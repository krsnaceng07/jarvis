"""Doctor contract runner — executes plugin doctor contracts.

Mirrors OpenClaw's ``src/doctor/doctor-runner.ts`` +
``src/doctor/contract.ts``.

Each plugin can optionally ship a ``doctor_contract`` — a callable
that checks the plugin's health / config and returns a list of
``DoctorFinding`` items.

The ``DoctorRunner`` collects all plugin doctor contracts from
``LoadResult.doctor_contracts`` and runs them on demand (via
``jarvis doctor`` CLI or the desktop Doctor status panel).

Findings are classified by severity:
  - ``ok``      — all good, no action needed
  - ``warning`` — optional but recommended action
  - ``error``   — required fix before the plugin works correctly
  - ``fix``     — the runner applied an automatic fix

Phase W3: sync execution only. Async doctor contracts land in Wave 4.
"""

from __future__ import annotations

import inspect
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

_log = logging.getLogger("jarvis.doctor")


# ── Finding severity ───────────────────────────────────────────────────


class Severity(str, Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    FIX = "fix"


# ── Finding ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DoctorFinding:
    """One finding from a doctor contract.

    Mirrors OpenClaw's ``DoctorFinding`` from
    ``src/doctor/contract.ts``.

    Attributes
    ----------
    plugin_id : str
        The extension that produced this finding.
    label : str
        Optional check label or legacy contract label.
    path : Path | str | None
        Optional file path associated with the finding.
    count : int | None
        Optional numeric count for legacy doctor checks.
    severity : Severity
        How serious the finding is.
    message : str
        Human-readable description.
    detail : str | None
        Optional extended detail / stack trace.
    details : dict[str, Any] | None
        Legacy compatibility payload used by old doctor checks.
    fix_applied : bool
        True when the runner automatically applied a fix.
    """

    plugin_id: str = ""
    label: str = ""
    path: Path | str | None = None
    count: int | None = None
    severity: Severity = Severity.OK
    message: str = ""
    detail: str | None = None
    details: dict[str, Any] | None = None
    fix_applied: bool = False


# ── DoctorContract compatibility shape ──────────────────────────────


@dataclass(slots=True)
class DoctorContract:
    """OpenClaw-compatible doctor contract descriptor.

    The runtime accepts both the high-level parsed shape (``id`` / ``version`` /
    ``detect`` / ``apply``) and the normalized runner shape (``plugin_id`` /
    ``check`` / ``fix``). This dataclass is consumed by ``DoctorRunner.add()``
    and by tests that instantiate a contract inline.
    """

    id: str = ""
    version: int = 1
    detect: Callable[..., Any] | None = None
    apply: Callable[[], None] | None = None
    enabled: bool = True


# ── DoctorReport ──────────────────────────────────────────────────────


@dataclass
class DoctorReport:
    """Aggregated results from running all doctor contracts.

    Attributes
    ----------
    findings : list[DoctorFinding]
        All findings in order.
    duration_ms : int
        Wall-clock time of the full run in milliseconds.
    plugin_count : int
        Number of plugins whose contracts were executed.
    """

    findings: list[DoctorFinding] = field(default_factory=list)
    duration_ms: int = 0
    plugin_count: int = 0
    contracts_run: list[str] = field(default_factory=list)
    contract_errors: list[str] = field(default_factory=list)

    @property
    def errors(self) -> list[DoctorFinding]:
        return [f for f in self.findings if f.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[DoctorFinding]:
        return [f for f in self.findings if f.severity == Severity.WARNING]

    @property
    def fixes(self) -> list[DoctorFinding]:
        return [f for f in self.findings if f.fix_applied]

    @property
    def is_healthy(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        parts = [f"{self.plugin_count} plugins checked in {self.duration_ms}ms"]
        if self.errors:
            parts.append(f"{len(self.errors)} error(s)")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning(s)")
        if self.fixes:
            parts.append(f"{len(self.fixes)} fix(es) applied")
        if self.is_healthy and not self.warnings:
            parts.append("all ok")
        return " · ".join(parts)


# ── DoctorRunner ───────────────────────────────────────────────────────


class DoctorRunner:
    """Executes plugin doctor contracts and aggregates findings.

    Mirrors OpenClaw's ``DoctorRunner`` from
    ``src/doctor/doctor-runner.ts``.

    Parameters
    ----------
    contracts : list[dict[str, Any]] | None
        The raw doctor contract dicts from ``LoadResult.doctor_contracts``.
        Each dict must have:
          - ``plugin_id`` (str)
          - ``check`` (callable[[], list[DoctorFinding] | DoctorFinding | None])
        Optionally:
          - ``fix``       (callable[[], None] | None)
          - ``enabled``   (bool, default True)
    """

    def __init__(self, contracts: list[dict[str, Any]] | None = None) -> None:
        contracts = contracts or []
        self._contracts: list[dict[str, Any]] = []
        for c in contracts:
            if isinstance(c, DoctorContract):
                self.add(c)
            elif isinstance(c, dict):
                self.add(c)
            else:
                continue

        _log.info(
            "doctor_runner: loaded %d contract(s) from %d raw entries",
            len(self._contracts),
            len(contracts),
        )

    def add(self, contract: DoctorContract | dict[str, Any]) -> None:
        raw = contract if isinstance(contract, dict) else _doctor_contract_to_dict(contract)
        canonical = _coerce_contract_dict(raw)
        if canonical is None:
            _log.debug("doctor: skipping invalid contract: %s", raw)
            return
        self._contracts.append(canonical)

    def add_raws(self, raws: list[dict[str, Any]]) -> None:
        for raw in raws:
            if not isinstance(raw, dict):
                continue
            self.add(raw)

    def list_ids(self) -> list[str]:
        return [contract["plugin_id"] for contract in self._contracts]

    def run_all(self, state_dir: Path, config: Any | None = None) -> DoctorReport:
        return self.run(state_dir=state_dir, config=config)

    def run_one(
        self,
        plugin_id: str,
        state_dir: Path,
        config: Any | None = None,
    ) -> DoctorReport:
        index = next(
            (i for i, c in enumerate(self._contracts) if c["plugin_id"] == plugin_id),
            None,
        )
        if index is None:
            report = DoctorReport(
                findings=[],
                duration_ms=0,
                plugin_count=len(self._contracts),
                contract_errors=[plugin_id],
            )
            return report
        contract = self._contracts[index]
        return self._run_contracts([contract], state_dir, config)

    def run(
        self,
        state_dir: Path | None = None,
        config: Any | None = None,
        *,
        apply_fixes: bool = False,
    ) -> DoctorReport:
        """Run all doctor contracts synchronously.

        Parameters
        ----------
        apply_fixes : bool
            If True, also call each contract's ``fix`` function when
            it is provided and the check produced errors.
        """
        return self._run_contracts(self._contracts, state_dir, config, apply_fixes=apply_fixes)

    def _run_contracts(
        self,
        contracts: list[dict[str, Any]],
        state_dir: Path | None,
        config: Any | None,
        apply_fixes: bool = False,
    ) -> DoctorReport:
        start = time.monotonic()
        all_findings: list[DoctorFinding] = []
        contract_errors: list[str] = []
        contracts_run: list[str] = []

        for contract in contracts:
            plugin_id = contract["plugin_id"]
            contracts_run.append(plugin_id)
            check_fn = contract["check"]
            fix_fn = contract.get("fix")
            enabled = contract.get("enabled", True)

            if not enabled:
                all_findings.append(
                    DoctorFinding(
                        plugin_id=plugin_id,
                        severity=Severity.OK,
                        message="doctor contract disabled",
                    )
                )
                continue

            try:
                raw = _invoke_check(check_fn, state_dir, config)
                findings = _normalize_findings(plugin_id, raw)
            except Exception as e:  # noqa: BLE001
                _log.warning("doctor: %s check() raised: %s", plugin_id, e)
                findings = [
                    DoctorFinding(
                        plugin_id=plugin_id,
                        severity=Severity.ERROR,
                        message=f"doctor check raised: {type(e).__name__}: {e}",
                        detail=str(e),
                    )
                ]
                contract_errors.append(plugin_id)

            has_errors = any(f.severity == Severity.ERROR for f in findings)
            if apply_fixes and has_errors and callable(fix_fn):
                try:
                    fix_fn()
                    _log.info("doctor: %s fix() applied", plugin_id)
                    findings = [
                        DoctorFinding(
                            plugin_id=f.plugin_id,
                            severity=f.severity,
                            message=f.message,
                            detail=f.detail,
                            fix_applied=True,
                        )
                        for f in findings
                    ]
                except Exception as fix_exc:  # noqa: BLE001
                    _log.warning("doctor: %s fix() raised: %s", plugin_id, fix_exc)
                    findings.append(
                        DoctorFinding(
                            plugin_id=plugin_id,
                            severity=Severity.ERROR,
                            message=f"fix() raised: {fix_exc}",
                        )
                    )
                    contract_errors.append(plugin_id)

            all_findings.extend(findings)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        report = DoctorReport(
            findings=all_findings,
            duration_ms=elapsed_ms,
            plugin_count=len(self._contracts),
            contracts_run=contracts_run,
            contract_errors=contract_errors,
        )
        _log.info("doctor: %s", report.summary())
        return report


def _coerce_contract_dict(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize the OpenClaw contract dict and legacy Phase-2 shapes."""
    if not isinstance(raw, dict):
        return None

    plugin_id = raw.get("plugin_id") or raw.get("id")
    if not plugin_id:
        return None

    check = raw.get("check") or raw.get("detect")
    if not callable(check):
        return None

    fix = raw.get("fix") or raw.get("apply")
    enabled = raw.get("enabled", True)
    return {
        "plugin_id": str(plugin_id),
        "check": check,
        "fix": fix if callable(fix) else None,
        "enabled": bool(enabled),
    }


def _doctor_contract_to_dict(contract: DoctorContract) -> dict[str, Any]:
    return {
        "plugin_id": contract.id,
        "check": contract.detect,
        "fix": contract.apply,
        "enabled": contract.enabled,
    }


def _invoke_check(
    check_fn: Callable[..., Any],
    state_dir: Path | None,
    config: Any | None,
) -> Any:
    if state_dir is None and config is None:
        return check_fn()
    try:
        return check_fn(state_dir, config)
    except TypeError:
        return check_fn()


def _normalize_findings(
    plugin_id: str, raw: Any
) -> list[DoctorFinding]:
    """Normalize a contract check() return value to a list of findings."""
    if raw is None:
        return [DoctorFinding(plugin_id=plugin_id, severity=Severity.OK, message="ok")]
    if isinstance(raw, DoctorFinding):
        return [raw]
    if isinstance(raw, list):
        result = []
        for item in raw:
            if isinstance(item, DoctorFinding):
                result.append(item)
            elif isinstance(item, dict):
                result.append(
                    DoctorFinding(
                        plugin_id=item.get("plugin_id", plugin_id),
                        label=item.get("label", ""),
                        path=item.get("path"),
                        count=item.get("count"),
                        severity=Severity(item.get("severity", "ok")),
                        message=item.get("message", ""),
                        detail=item.get("detail"),
                        details=item.get("details"),
                        fix_applied=item.get("fix_applied", False),
                    )
                )
        return result or [DoctorFinding(plugin_id=plugin_id, severity=Severity.OK, message="ok")]
    # Treat any truthy value as ok.
    return [DoctorFinding(plugin_id=plugin_id, severity=Severity.OK, message=str(raw))]


__all__ = [
    "DoctorContract",
    "DoctorFinding",
    "DoctorReport",
    "DoctorRunner",
    "Severity",
]
