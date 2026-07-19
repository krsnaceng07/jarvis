"""Doctor — runs every plugin's ``register_doctor_contract`` detections.

Mirrors OpenClaw's ``openclaw doctor`` command. A plugin registers a
doctor contract via ``api.register_doctor_contract(...)``; the host's
doctor runner calls each contract's ``detect(state_dir, config)`` and
prints a human-readable report.

The contracts live alongside plugins (each plugin owns its own
detection logic). The runner is the only place that knows how to
collect them all.

Phase 2 shape: 100% mirror of OpenClaw's doctor runner. The
runner-side API is ``DoctorRunner.run_all()``; CLI side is in
``apps/cli/src/jarvis_cli/doctor.py`` (Phase 2.5).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

_log = logging.getLogger("jarvis.doctor")


@dataclass(frozen=True, slots=True)
class DoctorFinding:
    """A single legacy-data finding reported by a plugin.

    Mirrors OpenClaw's ``MigrationDetection`` shape. Plugins return
    these from their contract's ``detect(state_dir, config)`` call.
    """

    label: str
    """Human-readable description (e.g. 'Legacy MARK XXXIX-OR reminders')."""

    path: Path
    """The file path the legacy data was found at."""

    count: int = 0
    """How many legacy items were found (0 means nothing to migrate)."""

    details: dict[str, Any] = field(default_factory=dict)
    """Optional structured details (timestamps, schema versions, etc.)."""


@dataclass(frozen=True, slots=True)
class DoctorContract:
    """A plugin-registered doctor contract.

    Mirrors OpenClaw's ``PluginDoctorStateMigration``. The runner
    calls ``detect(state_dir, config)`` for each registered contract.
    """

    id: str
    version: int
    detect: Any  # Callable[[Path, dict], list[DoctorFinding]]
    apply: Any | None = None  # Callable[[Path, dict], list[Change]]; optional
    owner_id: str = ""


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """The aggregate result of running every doctor contract."""

    findings: tuple[DoctorFinding, ...]
    contracts_run: tuple[str, ...]
    contract_errors: dict[str, str]  # contract_id -> error message

    def to_text(self) -> str:
        """Render as a human-readable multi-line report."""
        lines: list[str] = []
        lines.append("=== JARVIS Doctor ===\n")
        lines.append(f"Contracts run: {len(self.contracts_run)}")
        lines.append(f"Findings: {len(self.findings)}")
        if self.contract_errors:
            lines.append(f"Errors: {len(self.contract_errors)}")
        lines.append("")

        if self.findings:
            lines.append("## Findings\n")
            for f in self.findings:
                lines.append(f"  - {f.label}")
                lines.append(f"    path: {f.path}")
                if f.count:
                    lines.append(f"    count: {f.count}")
                if f.details:
                    for k, v in f.details.items():
                        lines.append(f"    {k}: {v}")
                lines.append("")

        if self.contract_errors:
            lines.append("## Contract errors\n")
            for cid, err in self.contract_errors.items():
                lines.append(f"  - {cid}: {err}")
            lines.append("")

        if not self.findings and not self.contract_errors:
            lines.append("No legacy data found. Workspace is clean.\n")

        return "\n".join(lines)


class DoctorRunner:
    """Runs every registered doctor contract and aggregates findings.

    Phase 2 host. Created once at session start; the host feeds it
    every contract collected from ``_load_plugins()``. The CLI
    (``jarvis doctor``) calls ``run_all()`` to produce a report.
    """

    def __init__(self) -> None:
        self._contracts: dict[str, DoctorContract] = {}

    def add(self, contract: DoctorContract) -> None:
        self._contracts[contract.id] = contract

    def add_raw(self, raw: dict[str, Any]) -> None:
        """Add a contract from a raw plugin dict (mirrors OpenClaw's API shape).

        Expects keys: ``id``, ``version``, ``detect``, optionally ``apply``.
        Stamps ``owner_id`` from the dict's ``_owner_id`` (set by
        the SDK's ``register_doctor_contract``).
        """
        if "id" not in raw or "version" not in raw or "detect" not in raw:
            raise ValueError(f"doctor contract missing required keys (id, version, detect): {raw}")
        contract = DoctorContract(
            id=raw["id"],
            version=int(raw["version"]),
            detect=raw["detect"],
            apply=raw.get("apply"),
            owner_id=raw.get("_owner_id", ""),
        )
        self.add(contract)

    def add_raws(self, raws: list[dict[str, Any]]) -> None:
        for r in raws:
            try:
                self.add_raw(r)
            except ValueError as e:
                _log.warning("doctor: skipping bad contract: %s", e)

    def list_ids(self) -> list[str]:
        return sorted(self._contracts.keys())

    def run_all(self, state_dir: Path, config: dict[str, Any] | None = None) -> DoctorReport:
        """Run every contract's ``detect()`` and collect findings."""
        cfg = config or {}
        findings: list[DoctorFinding] = []
        contracts_run: list[str] = []
        contract_errors: dict[str, str] = {}

        for cid, contract in self._contracts.items():
            try:
                contract_findings = contract.detect(state_dir, cfg) or []
            except Exception as e:
                _log.warning("doctor: contract %s raised: %s", cid, e)
                contract_errors[cid] = str(e)
                continue
            contracts_run.append(cid)
            findings.extend(contract_findings)

        return DoctorReport(
            findings=tuple(findings),
            contracts_run=tuple(contracts_run),
            contract_errors=contract_errors,
        )

    def run_one(
        self,
        contract_id: str,
        state_dir: Path,
        config: dict[str, Any] | None = None,
    ) -> DoctorReport:
        """Run a single contract by id."""
        if contract_id not in self._contracts:
            return DoctorReport(
                findings=(),
                contracts_run=(),
                contract_errors={contract_id: f"unknown contract: {contract_id!r}"},
            )
        # Wrap a single contract in a fresh runner so the report
        # attributes reflect just that contract.
        single = DoctorRunner()
        single.add(self._contracts[contract_id])
        return single.run_all(state_dir, config)


__all__ = [
    "DoctorContract",
    "DoctorFinding",
    "DoctorReport",
    "DoctorRunner",
]
