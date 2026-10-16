"""jarvis_learning.datasets.ood_policy — multi-mode OOD definitions and holdout registry.

Enforces:
- Explicit OOD modes: OOD_DOMAIN, OOD_APPLICATION, OOD_TOOL, etc.
- Historical holdout registry preventing OOD contamination from past training corpora.
- Distinguishes seen_in_training_corpus from seen_in_validation_only / evaluation_only.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum


class OODMode(StrEnum):
    OOD_DOMAIN = "ood_domain"
    OOD_APPLICATION = "ood_application"
    OOD_TOOL = "ood_tool"
    OOD_TASK_FAMILY = "ood_task_family"
    OOD_TARGET = "ood_target"
    OOD_DEVICE = "ood_device"
    OOD_COMPOSITIONAL = "ood_compositional"


class HistoricalOODScope(StrEnum):
    SEEN_IN_CURRENT_DATASET = "seen_in_current_dataset"
    SEEN_IN_PREVIOUS_DATASET = "seen_in_previous_dataset"
    SEEN_IN_TRAINING_CORPUS = "seen_in_training_corpus"
    SEEN_IN_VALIDATION_ONLY = "seen_in_validation_only"
    SEEN_IN_EVALUATION_ONLY = "seen_in_evaluation_only"


@dataclass(frozen=True, slots=True)
class OODHoldoutConfig:
    """Constraints for out-of-distribution partition selection."""

    mode: OODMode = OODMode.OOD_DOMAIN
    target_ratio: float = 0.10
    min_groups: int = 1
    min_samples: int = 5
    max_ratio: float = 0.25
    seed: int = 42
    holdout_ratio: float | None = None

    def __post_init__(self) -> None:
        if self.holdout_ratio is not None:
            object.__setattr__(self, "target_ratio", self.holdout_ratio)


@dataclass(frozen=True, slots=True)
class OODSelectionResult:
    """Result of OOD holdout selection."""

    mode: OODMode
    held_out_dimension: str
    held_out_values: tuple[str, ...]
    selected_group_keys: tuple[str, ...]
    sample_count: int
    selection_seed: int


class HistoricalOODRegistry:
    """Tracks identities seen across historical datasets to avoid OOD contamination."""

    def __init__(self) -> None:
        # identity_tag -> set of scopes where it was seen
        self._registry: dict[str, set[HistoricalOODScope]] = {}

    def register_identity(self, identity: str, scope: HistoricalOODScope) -> None:
        """Register an observed identity under a specific historical scope."""
        tag = identity.lower().strip()
        self._registry.setdefault(tag, set()).add(scope)

    def is_eligible_for_ood(self, identity: str) -> bool:
        """Return True if identity has NOT been used in training corpora or previous datasets.

        Identities seen in validation_only or evaluation_only remain eligible for OOD.
        """
        tag = identity.lower().strip()
        scopes = self._registry.get(tag, set())
        # Block if used in training corpus or previous trained dataset
        if HistoricalOODScope.SEEN_IN_TRAINING_CORPUS in scopes:
            return False
        if HistoricalOODScope.SEEN_IN_PREVIOUS_DATASET in scopes:
            return False
        return True

    def record_training_attributes(self, identities: list[str]) -> None:
        """Record identities as having been seen in a training corpus."""
        for ident in identities:
            self.register_identity(ident, HistoricalOODScope.SEEN_IN_TRAINING_CORPUS)

    def ingest_training_manifest(
        self,
        dataset_id: str,
        training_job_id: str,
        manifest_hash: str,
        sample_identities: list[str],
        domains: list[str] | None = None,
        applications: list[str] | None = None,
        tools: list[str] | None = None,
        task_families: list[str] | None = None,
        targets: list[str] | None = None,
    ) -> None:
        """Ingest training attributes from an immutable prior dataset manifest."""
        self.register_identity(f"ds:{dataset_id}", HistoricalOODScope.SEEN_IN_PREVIOUS_DATASET)
        self.register_identity(f"job:{training_job_id}", HistoricalOODScope.SEEN_IN_TRAINING_CORPUS)
        self.register_identity(
            f"mhash:{manifest_hash}", HistoricalOODScope.SEEN_IN_PREVIOUS_DATASET
        )

        for s in sample_identities:
            self.register_identity(s, HistoricalOODScope.SEEN_IN_TRAINING_CORPUS)
        for d in domains or []:
            self.register_identity(f"dom:{d}", HistoricalOODScope.SEEN_IN_TRAINING_CORPUS)
            self.register_identity(d, HistoricalOODScope.SEEN_IN_TRAINING_CORPUS)
        for a in applications or []:
            self.register_identity(f"app:{a}", HistoricalOODScope.SEEN_IN_TRAINING_CORPUS)
            self.register_identity(a, HistoricalOODScope.SEEN_IN_TRAINING_CORPUS)
        for t in tools or []:
            self.register_identity(f"tool:{t}", HistoricalOODScope.SEEN_IN_TRAINING_CORPUS)
            self.register_identity(t, HistoricalOODScope.SEEN_IN_TRAINING_CORPUS)
        for tf in task_families or []:
            self.register_identity(f"task:{tf}", HistoricalOODScope.SEEN_IN_TRAINING_CORPUS)
            self.register_identity(tf, HistoricalOODScope.SEEN_IN_TRAINING_CORPUS)
        for tgt in targets or []:
            self.register_identity(f"tgt:{tgt}", HistoricalOODScope.SEEN_IN_TRAINING_CORPUS)
            self.register_identity(tgt, HistoricalOODScope.SEEN_IN_TRAINING_CORPUS)

    def is_historically_contaminated(self, identity: str) -> bool:
        """Check if an identity has historical training contamination."""
        return not self.is_eligible_for_ood(identity)


class OODPolicySelector:
    """Selects valid OOD holdout groups adhering to mode and historical registry."""

    def __init__(self, registry: HistoricalOODRegistry | None = None) -> None:
        self._registry = registry or HistoricalOODRegistry()

    def select_ood_groups(
        self,
        group_attributes: dict[str, set[str]],
        config: OODHoldoutConfig,
    ) -> OODSelectionResult:
        """Select groups for the OOD test split based on config."""
        prefix_map = {
            OODMode.OOD_DOMAIN: "dom:",
            OODMode.OOD_APPLICATION: "app:",
            OODMode.OOD_TOOL: "tool:",
            OODMode.OOD_TASK_FAMILY: "task:",
            OODMode.OOD_TARGET: "tgt:",
            OODMode.OOD_DEVICE: "dev:",
            OODMode.OOD_COMPOSITIONAL: "comp:",
        }
        dim_prefix = prefix_map.get(config.mode, "dom:")

        # Find all distinct attribute values of this dimension across groups
        val_to_groups: dict[str, list[str]] = {}
        for grp_key, attrs in group_attributes.items():
            for attr in attrs:
                if attr.startswith(dim_prefix):
                    val = attr[len(dim_prefix) :]
                    if self._registry.is_eligible_for_ood(val):
                        val_to_groups.setdefault(val, []).append(grp_key)

        if not val_to_groups or len(group_attributes) < 4:
            # Not enough independent groups to form a statistically sound OOD split
            return OODSelectionResult(
                mode=config.mode,
                held_out_dimension=dim_prefix[:-1],
                held_out_values=(),
                selected_group_keys=(),
                sample_count=0,
                selection_seed=config.seed,
            )

        rng = random.Random(config.seed)
        candidate_values = sorted(val_to_groups.keys())
        rng.shuffle(candidate_values)

        total_groups = len(group_attributes)
        max_allowed_groups = max(1, int(total_groups * config.max_ratio))

        selected_vals: list[str] = []
        selected_groups: set[str] = set()

        for val in candidate_values:
            val_groups = val_to_groups[val]
            # Check if adding this value exceeds maximum OOD allowance
            if len(selected_groups) + len(val_groups) > max_allowed_groups and selected_groups:
                continue

            selected_vals.append(val)
            selected_groups.update(val_groups)

            if len(selected_groups) >= config.min_groups:
                break

        return OODSelectionResult(
            mode=config.mode,
            held_out_dimension=dim_prefix[:-1],
            held_out_values=tuple(selected_vals),
            selected_group_keys=tuple(sorted(selected_groups)),
            sample_count=len(selected_groups),
            selection_seed=config.seed,
        )
