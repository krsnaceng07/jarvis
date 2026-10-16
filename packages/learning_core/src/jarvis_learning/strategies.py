"""jarvis_learning.strategies — learned task strategies and failure patterns.

A strategy captures a proven approach: given a recognized intent and
context, which tool/arguments/verification steps reliably succeed.
Failure patterns are the inverse: known anti-patterns with preferred
alternatives.

Both are stored in SQLite and retrieved by semantic match against
the current task.
"""

from __future__ import annotations

from enum import Enum
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from .experience import generate_id, now_ms

logger = logging.getLogger(__name__)


class ScopeLevel(str, Enum):
    """Scoped applicability levels for failure patterns."""

    EXACT_ARGUMENTS = "exact_arguments"
    SAME_APPLICATION = "same_application"
    SAME_DEVICE = "same_device"
    SAME_DOMAIN = "same_domain"
    SAME_HOST = "same_host"
    GLOBAL = "global"


@dataclass(frozen=True, slots=True)
class FailureScopeDimensions:
    """Multi-dimensional contextual footprint for scoped failure avoidance."""

    scope: ScopeLevel = ScopeLevel.EXACT_ARGUMENTS
    domain: str = ""
    host: str = ""
    application: str = ""
    device_id: str = ""


class StrategyStatus(str, Enum):
    """Lifecycle state of a learned strategy."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    INVALIDATED = "INVALIDATED"
    REQUIRES_REVALIDATION = "REQUIRES_REVALIDATION"


@dataclass(frozen=True, slots=True)
class Strategy:
    """A reusable strategy learned from successful task executions."""

    id: str
    created_at: int
    updated_at: int
    intent: str
    context_conditions: dict[str, Any] = field(default_factory=dict)
    preferred_action: str = ""
    tool: str = ""
    argument_pattern: dict[str, Any] = field(default_factory=dict)
    verification: str = ""
    fallback: str = ""
    success_count: int = 0
    failure_count: int = 0
    confidence: float = 0.5
    last_used: int = 0
    # Wave 5 Lifecycle & Provenance additions
    status: str = "active"
    origin: str = "reflection"
    source_experience_ids: tuple[str, ...] = ()
    source_session_ids: tuple[str, ...] = ()
    created_by: str = "learning_pipeline"
    manual_override: bool = False
    verified: bool = True
    last_verified_success_ms: int = 0
    last_verified_failure_ms: int = 0
    consecutive_failures: int = 0
    risk_tier: int = 1
    bayesian_state: dict[str, Any] = field(default_factory=dict)
    precondition_contract: dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Fraction of uses that succeeded."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    @property
    def is_reliable(self) -> bool:
        """A strategy is reliable when it has enough evidence and high success rate."""
        return (
            self.status.lower() == StrategyStatus.ACTIVE.value
            and self.success_count >= 3
            and self.success_rate >= 0.7
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for SQLite storage."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "intent": self.intent,
            "context_conditions": json.dumps(self.context_conditions),
            "preferred_action": self.preferred_action,
            "tool": self.tool,
            "argument_pattern": json.dumps(self.argument_pattern),
            "verification": self.verification,
            "fallback": self.fallback,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "confidence": self.confidence,
            "last_used": self.last_used,
            "status": self.status,
            "origin": self.origin,
            "source_experience_ids": json.dumps(list(self.source_experience_ids)),
            "source_session_ids": json.dumps(list(self.source_session_ids)),
            "created_by": self.created_by,
            "manual_override": 1 if self.manual_override else 0,
            "verified": 1 if self.verified else 0,
            "last_verified_success_ms": self.last_verified_success_ms,
            "last_verified_failure_ms": self.last_verified_failure_ms,
            "consecutive_failures": self.consecutive_failures,
            "risk_tier": self.risk_tier,
            "bayesian_state": json.dumps(self.bayesian_state),
            "precondition_contract": json.dumps(self.precondition_contract),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Strategy:
        """Deserialize from a SQLite row dict."""
        conditions = data.get("context_conditions", "{}")
        if isinstance(conditions, str):
            conditions = json.loads(conditions)
        args = data.get("argument_pattern", "{}")
        if isinstance(args, str):
            args = json.loads(args)

        exp_ids = data.get("source_experience_ids", "[]")
        if isinstance(exp_ids, str):
            exp_ids = tuple(json.loads(exp_ids))
        elif isinstance(exp_ids, (list, tuple)):
            exp_ids = tuple(exp_ids)
        else:
            exp_ids = ()

        sess_ids = data.get("source_session_ids", "[]")
        if isinstance(sess_ids, str):
            sess_ids = tuple(json.loads(sess_ids))
        elif isinstance(sess_ids, (list, tuple)):
            sess_ids = tuple(sess_ids)
        else:
            sess_ids = ()

        manual = data.get("manual_override", False)
        if isinstance(manual, int):
            manual = bool(manual)

        verified = data.get("verified", True)
        if isinstance(verified, int):
            verified = bool(verified)

        bayes_state = data.get("bayesian_state", "{}")
        if isinstance(bayes_state, str):
            try:
                bayes_state = json.loads(bayes_state)
            except Exception:
                bayes_state = {}

        precond = data.get("precondition_contract", "{}")
        if isinstance(precond, str):
            try:
                precond = json.loads(precond)
            except Exception:
                precond = {}

        return cls(
            id=data["id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            intent=data["intent"],
            context_conditions=conditions,
            preferred_action=data.get("preferred_action", ""),
            tool=data.get("tool", ""),
            argument_pattern=args,
            verification=data.get("verification", ""),
            fallback=data.get("fallback", ""),
            success_count=data.get("success_count", 0),
            failure_count=data.get("failure_count", 0),
            confidence=data.get("confidence", 0.5),
            last_used=data.get("last_used", 0),
            status=data.get("status", StrategyStatus.ACTIVE.value),
            origin=data.get("origin", "reflection"),
            source_experience_ids=exp_ids,
            source_session_ids=sess_ids,
            created_by=data.get("created_by", "learning_pipeline"),
            manual_override=manual,
            verified=verified,
            last_verified_success_ms=data.get("last_verified_success_ms", 0),
            last_verified_failure_ms=data.get("last_verified_failure_ms", 0),
            consecutive_failures=int(data.get("consecutive_failures", 0)),
            risk_tier=int(data.get("risk_tier", 1)),
            bayesian_state=bayes_state,
            precondition_contract=precond,
        )


@dataclass(frozen=True, slots=True)
class FailurePattern:
    """A learned anti-pattern: what NOT to do, with contextual scope."""

    id: str
    created_at: int
    pattern_name: str
    condition: dict[str, Any] = field(default_factory=dict)
    bad_action: str = ""
    preferred_action: str = ""
    occurrence_count: int = 0
    confidence: float = 0.5
    # Wave 5 Scoped applicability additions
    scope: str = "exact_arguments"  # "exact_arguments", "same_application", "same_device", "global"
    recovery_strategy: str = ""
    expiration_ms: int | None = None
    tool_name: str = ""
    argument_signature: str = ""
    environment_fingerprint: str = ""
    intent_signature: str = ""

    def is_applicable(
        self,
        candidate_tool: str,
        candidate_args: dict[str, Any] | None = None,
        candidate_env: str = "",
    ) -> bool:
        """Determines whether this failure pattern applies to the proposed action."""
        # 1. Tool name must match if specified
        target_tool = self.tool_name or self.bad_action
        if target_tool and target_tool != candidate_tool:
            return False

        # 2. Check expiration if set
        if self.expiration_ms and now_ms() > self.expiration_ms:
            return False

        # 3. Check scope
        if self.scope in ("global", ScopeLevel.GLOBAL.value):
            return True
        elif self.scope in ("same_application", ScopeLevel.SAME_APPLICATION.value):
            return self.condition.get("application") == (candidate_args or {}).get("application")
        elif self.scope in ("same_device", ScopeLevel.SAME_DEVICE.value):
            return self.environment_fingerprint == candidate_env
        elif self.scope in ("same_domain", ScopeLevel.SAME_DOMAIN.value):
            target_domain = self.condition.get("domain", "")
            cand_domain = str(
                (candidate_args or {}).get("domain") or (candidate_args or {}).get("url") or ""
            )
            return bool(target_domain and target_domain in cand_domain)
        elif self.scope in ("same_host", ScopeLevel.SAME_HOST.value):
            target_host = self.condition.get("host", "")
            cand_host = str((candidate_args or {}).get("host") or candidate_env)
            return bool(target_host and target_host in cand_host)
        elif self.scope in ("exact_arguments", ScopeLevel.EXACT_ARGUMENTS.value):
            if not self.argument_signature or not candidate_args:
                return True
            candidate_sig = json.dumps(candidate_args, sort_keys=True)
            return self.argument_signature == candidate_sig

        return True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for SQLite storage."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "pattern_name": self.pattern_name,
            "condition": json.dumps(self.condition),
            "bad_action": self.bad_action,
            "preferred_action": self.preferred_action,
            "occurrence_count": self.occurrence_count,
            "confidence": self.confidence,
            "scope": self.scope,
            "recovery_strategy": self.recovery_strategy,
            "expiration_ms": self.expiration_ms or 0,
            "tool_name": self.tool_name,
            "argument_signature": self.argument_signature,
            "environment_fingerprint": self.environment_fingerprint,
            "intent_signature": self.intent_signature,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FailurePattern:
        """Deserialize from a SQLite row dict."""
        cond = data.get("condition", "{}")
        if isinstance(cond, str):
            cond = json.loads(cond)
        return cls(
            id=data["id"],
            created_at=data["created_at"],
            pattern_name=data["pattern_name"],
            condition=cond,
            bad_action=data.get("bad_action", ""),
            preferred_action=data.get("preferred_action", ""),
            occurrence_count=data.get("occurrence_count", 0),
            confidence=data.get("confidence", 0.5),
            scope=data.get("scope", "exact_arguments"),
            recovery_strategy=data.get("recovery_strategy", ""),
            expiration_ms=data.get("expiration_ms") or None,
            tool_name=data.get("tool_name", ""),
            argument_signature=data.get("argument_signature", ""),
            environment_fingerprint=data.get("environment_fingerprint", ""),
            intent_signature=data.get("intent_signature", ""),
        )


class StrategyStore:
    """In-memory + SQLite strategy and failure pattern store with confidence decay."""

    def __init__(self) -> None:
        self._strategies: dict[str, Strategy] = {}
        self._failure_patterns: dict[str, FailurePattern] = {}

    def add_strategy(self, strategy: Strategy) -> None:
        """Add or replace a strategy."""
        self._strategies[strategy.id] = strategy
        logger.debug("strategy stored: id=%s intent=%s", strategy.id, strategy.intent)

    def create_strategy_from_experience(
        self,
        intent: str,
        tool: str,
        argument_pattern: dict[str, Any] | None = None,
        preferred_action: str = "",
        context_conditions: dict[str, Any] | None = None,
        verification: str = "",
        fallback: str = "",
        confidence: float = 0.5,
        success_count: int = 1,
        failure_count: int = 0,
        **kwargs: Any,
    ) -> Strategy:
        """Create and store a Strategy, initializing with 1 success count."""
        ts = now_ms()
        strat_id = generate_id()
        strategy = Strategy(
            id=strat_id,
            created_at=ts,
            updated_at=ts,
            intent=intent,
            context_conditions=context_conditions or {},
            preferred_action=preferred_action or tool,
            tool=tool,
            argument_pattern=argument_pattern or {},
            verification=verification,
            fallback=fallback,
            success_count=success_count,
            failure_count=failure_count,
            confidence=confidence,
            last_used=ts,
            status=StrategyStatus.ACTIVE.value,
            origin="reflection",
            source_experience_ids=tuple(kwargs.get("source_experience_ids", ())),
            source_session_ids=tuple(kwargs.get("source_session_ids", ())),
            created_by="learning_pipeline",
            manual_override=False,
            verified=True,
            last_verified_success_ms=ts,
        )
        self.add_strategy(strategy)
        return strategy

    def create_failure_pattern(
        self,
        pattern_name: str,
        bad_action: str,
        preferred_action: str = "",
        condition: dict[str, Any] | None = None,
        confidence: float = 0.5,
        **kwargs: Any,
    ) -> FailurePattern:
        """Create and store a FailurePattern."""
        ts = now_ms()
        fp_id = generate_id()
        pattern = FailurePattern(
            id=fp_id,
            created_at=ts,
            pattern_name=pattern_name,
            condition=condition or {},
            bad_action=bad_action,
            preferred_action=preferred_action,
            occurrence_count=1,
            confidence=confidence,
            tool_name=kwargs.get(
                "tool_name",
                bad_action.split("(")[0].split()[0]
                if "(" in bad_action or " " in bad_action
                else bad_action,
            ),
            recovery_strategy=kwargs.get("recovery_strategy", ""),
            scope=kwargs.get("scope", ScopeLevel.EXACT_ARGUMENTS.value),
        )
        self.add_failure_pattern(pattern)
        return pattern

    def check_failure_patterns(
        self,
        action: str,
        context: dict[str, Any] | None = None,
    ) -> list[FailurePattern]:
        """Check if action matches any known failure pattern."""
        matches: list[FailurePattern] = []
        action_lower = action.lower()
        for p in self._failure_patterns.values():
            p_bad = p.bad_action.lower()
            p_tool = p.tool_name.lower()
            if action_lower in p_bad or p_bad in action_lower or action_lower == p_tool:
                matches.append(p)
        return sorted(matches, key=lambda p: p.confidence, reverse=True)

    def load_strategies(self, strategies: list[Strategy]) -> None:
        """Bulk load strategies into memory."""
        for s in strategies:
            self._strategies[s.id] = s

    def load_failure_patterns(self, patterns: list[FailurePattern]) -> None:
        """Bulk load failure patterns into memory."""
        for p in patterns:
            self._failure_patterns[p.id] = p

    def get_strategy(self, strategy_id: str) -> Strategy | None:
        """Retrieve a single strategy by id."""
        return self._strategies.get(strategy_id)

    def find_strategies_for_intent(self, intent: str) -> list[Strategy]:
        """Return active strategies matching intent, ordered by confidence * success_rate."""
        intent_lower = intent.lower()
        active_matches = []
        for s in self._strategies.values():
            if s.status.lower() != StrategyStatus.ACTIVE.value:
                continue
            s_intent = s.intent.lower()
            # Match if either is a substring of the other, or any significant token overlaps
            if intent_lower in s_intent or s_intent in intent_lower:
                active_matches.append(s)
            elif any(len(w) > 3 and w in intent_lower for w in s_intent.split()):
                active_matches.append(s)

        return sorted(
            active_matches,
            key=lambda s: s.confidence * s.success_rate,
            reverse=True,
        )

    def record_strategy_outcome(self, strategy_id: str, *, succeeded: bool) -> Strategy | None:
        """Update success/failure counts, apply confidence decay, and suspend if failing repeatedly."""
        old = self._strategies.get(strategy_id)
        if old is None:
            return None

        ts = now_ms()
        new_success = old.success_count + (1 if succeeded else 0)
        new_failure = old.failure_count + (0 if succeeded else 1)
        total = new_success + new_failure

        # Base confidence update
        new_confidence = new_success / total if total > 0 else 0.5

        # Check status transition & consecutive failures
        new_status = old.status
        if not succeeded:
            new_consecutive_failures = old.consecutive_failures + 1
            # Decay confidence by 15% on each failure
            new_confidence = max(0.1, new_confidence * 0.85)
            # Automatic rollback circuit breaker: >= 2 consecutive failures suspends immediately!
            if new_consecutive_failures >= 2 or (new_failure >= 3 and (new_success / total) < 0.4):
                new_status = StrategyStatus.SUSPENDED.value
                logger.warning(
                    "strategy suspended due to repeated/consecutive failures: id=%s consecutive=%d",
                    old.id,
                    new_consecutive_failures,
                )
        else:
            new_consecutive_failures = 0

        updated = Strategy(
            id=old.id,
            created_at=old.created_at,
            updated_at=ts,
            intent=old.intent,
            context_conditions=old.context_conditions,
            preferred_action=old.preferred_action,
            tool=old.tool,
            argument_pattern=old.argument_pattern,
            verification=old.verification,
            fallback=old.fallback,
            success_count=new_success,
            failure_count=new_failure,
            confidence=new_confidence,
            last_used=ts,
            status=new_status,
            origin=old.origin,
            source_experience_ids=old.source_experience_ids,
            source_session_ids=old.source_session_ids,
            created_by=old.created_by,
            manual_override=old.manual_override,
            verified=old.verified,
            last_verified_success_ms=ts if succeeded else old.last_verified_success_ms,
            last_verified_failure_ms=ts if not succeeded else old.last_verified_failure_ms,
            consecutive_failures=new_consecutive_failures,
            risk_tier=old.risk_tier,
            bayesian_state=old.bayesian_state,
            precondition_contract=old.precondition_contract,
        )
        self._strategies[strategy_id] = updated
        return updated

    def quarantine_strategy(self, strategy_id: str, reason: str = "") -> Strategy | None:
        """Quarantine a strategy by suspending it."""
        old = self._strategies.get(strategy_id)
        if old is None:
            return None
        ts = now_ms()
        updated = Strategy(
            id=old.id,
            created_at=old.created_at,
            updated_at=ts,
            intent=old.intent,
            context_conditions=old.context_conditions,
            preferred_action=old.preferred_action,
            tool=old.tool,
            argument_pattern=old.argument_pattern,
            verification=old.verification,
            fallback=old.fallback,
            success_count=old.success_count,
            failure_count=old.failure_count,
            confidence=0.0,
            last_used=old.last_used,
            status=StrategyStatus.SUSPENDED.value,
            origin=old.origin,
            source_experience_ids=old.source_experience_ids,
            source_session_ids=old.source_session_ids,
            created_by=old.created_by,
            manual_override=old.manual_override,
            verified=old.verified,
            last_verified_success_ms=old.last_verified_success_ms,
            last_verified_failure_ms=ts,
            consecutive_failures=old.consecutive_failures + 1,
            risk_tier=old.risk_tier,
            bayesian_state=old.bayesian_state,
            precondition_contract=old.precondition_contract,
        )
        self._strategies[strategy_id] = updated
        return updated

    # ── Failure Patterns ──────────────────────────────────────

    def add_failure_pattern(self, pattern: FailurePattern) -> None:
        """Add or replace a failure pattern."""
        self._failure_patterns[pattern.id] = pattern

    def get_failure_pattern(self, pattern_id: str) -> FailurePattern | None:
        return self._failure_patterns.get(pattern_id)

    def find_failure_patterns_for_action(
        self, action: str, tool_args: dict[str, Any] | None = None, env: str = ""
    ) -> list[FailurePattern]:
        """Find matching failure patterns that are actively applicable to context."""
        matches: list[FailurePattern] = []
        for p in self._failure_patterns.values():
            if p.bad_action == action or p.tool_name == action:
                if p.is_applicable(
                    candidate_tool=action, candidate_args=tool_args, candidate_env=env
                ):
                    matches.append(p)
        return sorted(matches, key=lambda p: p.confidence, reverse=True)

    def all_strategies(self) -> list[Strategy]:
        return list(self._strategies.values())

    def all_failure_patterns(self) -> list[FailurePattern]:
        return list(self._failure_patterns.values())

    def clear(self) -> None:
        self._strategies.clear()
        self._failure_patterns.clear()
