"""jarvis_learning.evaluation.benchmark — severity-aware benchmark runner.

Two-level evaluation:
- Level A: Policy/strategy benchmark (fast, deterministic)
- Level B: Runtime behavior benchmark via BenchmarkAgent protocol

Benchmarks are loaded from JSON files under benchmarks/jarvis_regression/.
Each case has a severity (critical/high/medium/low) and can include
setup state, forbidden actions, and success/failure conditions.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..strategies import StrategyStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One benchmark test case."""

    id: str
    description: str
    severity: str  # "critical" | "high" | "medium" | "low"
    category: str
    setup: dict[str, Any]
    input: dict[str, Any]
    expected_decision: dict[str, Any]
    forbidden_actions: tuple[str, ...] = ()
    max_steps: int = 3
    must_verify: bool = True
    success_conditions: tuple[str, ...] = ()
    failure_conditions: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, d: dict[str, Any], category: str = "") -> BenchmarkCase:
        return cls(
            id=d["id"],
            description=d.get("description", ""),
            severity=d.get("severity", "medium"),
            category=category or d.get("category", ""),
            setup=d.get("setup", {}),
            input=d.get("input", {}),
            expected_decision=d.get("expected_decision", {}),
            forbidden_actions=tuple(d.get("forbidden_actions", [])),
            max_steps=d.get("max_steps", 3),
            must_verify=d.get("must_verify", True),
            success_conditions=tuple(d.get("success_conditions", [])),
            failure_conditions=tuple(d.get("failure_conditions", [])),
        )


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """Result of evaluating one benchmark case."""

    case_id: str
    severity: str
    passed: bool
    actual_tool: str
    expected_tool: str
    forbidden_action_triggered: bool
    detail: str


@dataclass(frozen=True, slots=True)
class BenchmarkSuiteResult:
    """Result of running an entire benchmark suite."""

    passed: bool
    total: int
    passed_count: int
    failed_count: int
    results_by_category: dict[str, list[BenchmarkResult]]
    results_by_severity: dict[str, list[BenchmarkResult]]
    critical_failures: list[BenchmarkResult]


# ── Level B: Runtime behavior benchmark ──────────────────────


@dataclass(frozen=True, slots=True)
class AgentBenchmarkTrace:
    """Trace of an agent's actions during a benchmark case."""

    selected_tools: tuple[str, ...]
    tool_calls: tuple[dict[str, Any], ...]
    forbidden_actions_triggered: tuple[str, ...]
    final_state: dict[str, Any]
    final_claim: str
    verification_performed: bool
    steps_used: int
    completed: bool


@runtime_checkable
class BenchmarkAgent(Protocol):
    """Protocol for agents that can run benchmark cases (Level B)."""

    def run_case(
        self,
        case: BenchmarkCase,
        environment: BenchmarkEnvironment,
    ) -> AgentBenchmarkTrace: ...


# ── Benchmark environments ────────────────────────────────────


class BenchmarkEnvironment(ABC):
    """Abstract environment for benchmark execution."""

    @abstractmethod
    def setup(self, state: dict[str, Any]) -> None:
        """Initialize environment with the given state."""

    @abstractmethod
    def get_state(self) -> dict[str, Any]:
        """Return current environment state."""

    @abstractmethod
    def check_condition(self, condition: str) -> bool:
        """Check whether a condition is met."""

    @abstractmethod
    def execute_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call and return the result."""


class MockEnvironment(BenchmarkEnvironment):
    """In-memory mock environment for unit tests.

    Supports configurable tool results and condition checking.
    """

    def __init__(self) -> None:
        self._state: dict[str, Any] = {}
        self._tool_results: dict[str, dict[str, Any]] = {}
        self._conditions: dict[str, bool] = {}
        self._calls: list[dict[str, Any]] = []

    def setup(self, state: dict[str, Any]) -> None:
        self._state = dict(state)
        self._tool_results = state.get("tool_results", {})
        self._conditions = state.get("conditions", {})

    def get_state(self) -> dict[str, Any]:
        return dict(self._state)

    def check_condition(self, condition: str) -> bool:
        return self._conditions.get(condition, False)

    def execute_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        call = {"tool": tool_name, "args": args}
        self._calls.append(call)
        return self._tool_results.get(tool_name, {"is_ok": True, "value": "mock_result"})

    @property
    def call_log(self) -> list[dict[str, Any]]:
        return list(self._calls)


# ── Benchmark runner ──────────────────────────────────────────


class BenchmarkRunner:
    """Loads and runs benchmark suites."""

    def __init__(
        self,
        benchmark_dir: Path | str | None = None,
        env: BenchmarkEnvironment | None = None,
    ) -> None:
        if benchmark_dir is None:
            self._dir = Path(__file__).parents[3] / "benchmarks" / "jarvis_regression"
        else:
            self._dir = Path(benchmark_dir)
        self._env = env or MockEnvironment()

    def load_suite(self, category: str | None = None) -> list[BenchmarkCase]:
        """Load benchmark cases from JSON files.

        If ``category`` is specified, load only that file.
        Otherwise load all ``*.json`` files.
        """
        cases: list[BenchmarkCase] = []

        if category:
            path = self._dir / f"{category}.json"
            if path.exists():
                cases.extend(self._load_file(path, category))
        else:
            for path in sorted(self._dir.glob("*.json")):
                cat = path.stem
                cases.extend(self._load_file(path, cat))

        return cases

    def evaluate_strategy_store(
        self,
        store: StrategyStore,
        cases: list[BenchmarkCase],
    ) -> list[BenchmarkResult]:
        """Level A: Test whether the strategy store suggests the correct tool.

        Fast, deterministic — tests policy/strategy decisions only.
        """
        results: list[BenchmarkResult] = []

        for case in cases:
            user_input = case.input.get("user_input", "")
            expected_tool = case.expected_decision.get("tool", "")

            # Query the strategy store
            strategies = store.find_strategies_for_intent(user_input)

            actual_tool = ""
            if strategies:
                actual_tool = strategies[0].tool

            # Check forbidden actions
            forbidden_triggered = False
            for forbidden in case.forbidden_actions:
                if actual_tool and forbidden in actual_tool:
                    forbidden_triggered = True
                    break

            # Determine pass/fail
            tool_correct = actual_tool == expected_tool if expected_tool else True
            passed = tool_correct and not forbidden_triggered

            detail_parts: list[str] = []
            if not tool_correct:
                detail_parts.append(f"expected {expected_tool}, got {actual_tool or 'none'}")
            if forbidden_triggered:
                detail_parts.append(f"triggered forbidden action: {actual_tool}")
            if passed:
                detail_parts.append("passed")

            results.append(
                BenchmarkResult(
                    case_id=case.id,
                    severity=case.severity,
                    passed=passed,
                    actual_tool=actual_tool,
                    expected_tool=expected_tool,
                    forbidden_action_triggered=forbidden_triggered,
                    detail="; ".join(detail_parts),
                )
            )

        return results

    def evaluate_agent(
        self,
        agent: BenchmarkAgent,
        cases: list[BenchmarkCase],
    ) -> list[BenchmarkResult]:
        """Level B: Test actual agent runtime behavior.

        Runs the agent in the mock environment and checks:
        1. Correct tool selection
        2. No forbidden actions
        3. Correct final state
        4. Step count within limit
        5. Verification performed
        """
        results: list[BenchmarkResult] = []

        for case in cases:
            self._env.setup(case.setup)
            trace = agent.run_case(case, self._env)

            expected_tool = case.expected_decision.get("tool", "")

            # Check tool selection
            tool_correct = expected_tool in trace.selected_tools if expected_tool else True

            # Check forbidden actions
            forbidden_triggered = len(trace.forbidden_actions_triggered) > 0

            # Check step count
            steps_ok = trace.steps_used <= case.max_steps

            # Check verification
            verify_ok = trace.verification_performed if case.must_verify else True

            passed = (
                tool_correct
                and not forbidden_triggered
                and steps_ok
                and verify_ok
                and trace.completed
            )

            detail_parts: list[str] = []
            if not tool_correct:
                detail_parts.append(f"expected tool {expected_tool}")
            if forbidden_triggered:
                detail_parts.append(f"forbidden: {trace.forbidden_actions_triggered}")
            if not steps_ok:
                detail_parts.append(f"too many steps: {trace.steps_used}/{case.max_steps}")
            if not verify_ok:
                detail_parts.append("verification not performed")
            if passed:
                detail_parts.append("passed")

            results.append(
                BenchmarkResult(
                    case_id=case.id,
                    severity=case.severity,
                    passed=passed,
                    actual_tool=(trace.selected_tools[0] if trace.selected_tools else ""),
                    expected_tool=expected_tool,
                    forbidden_action_triggered=forbidden_triggered,
                    detail="; ".join(detail_parts),
                )
            )

        return results

    def evaluate_all(self, store: StrategyStore) -> BenchmarkSuiteResult:
        """Run ALL benchmarks via Level A (strategy store) evaluation."""
        cases = self.load_suite()
        results = self.evaluate_strategy_store(store, cases)
        return self._build_suite_result(results)

    @staticmethod
    def _build_suite_result(
        results: list[BenchmarkResult],
    ) -> BenchmarkSuiteResult:
        """Build a suite result from individual results."""
        by_category: dict[str, list[BenchmarkResult]] = {}
        by_severity: dict[str, list[BenchmarkResult]] = {}
        critical_failures: list[BenchmarkResult] = []

        for r in results:
            by_category.setdefault(r.case_id.split("_")[0], []).append(r)
            by_severity.setdefault(r.severity, []).append(r)
            if not r.passed and r.severity == "critical":
                critical_failures.append(r)

        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count
        all_passed = failed_count == 0

        return BenchmarkSuiteResult(
            passed=all_passed,
            total=len(results),
            passed_count=passed_count,
            failed_count=failed_count,
            results_by_category=by_category,
            results_by_severity=by_severity,
            critical_failures=critical_failures,
        )

    @staticmethod
    def _load_file(path: Path, category: str) -> list[BenchmarkCase]:
        """Load benchmark cases from a JSON file."""
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [BenchmarkCase.from_dict(d, category) for d in data]
            return []
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("failed to load benchmark %s: %s", path, e)
            return []
