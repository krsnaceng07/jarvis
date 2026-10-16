"""jarvis_learning.datasets.split — hierarchical zero-leakage stratified splitting.

Enforces:
- Transitive connected-component grouping via Disjoint-Set (Union-Find).
- 5 primary partitions: train, validation, test (in-distribution),
  ood_test (out-of-distribution), golden_holdout, plus challenge.
- Multi-mode OOD holdouts based on OODPolicySelector.
- Zero leakage across sessions, episodes, devices, targets, or lineage groups.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Sequence

from .leakage_groups import LeakageGroupBuilder, LeakageIdentity
from .ood_policy import (
    HistoricalOODRegistry,
    OODHoldoutConfig,
    OODPolicySelector,
    OODSelectionResult,
)
from .schema import DatasetSample


@dataclass(frozen=True, slots=True)
class SplitResult:
    """Result of hierarchical grouped splitting."""

    train: list[DatasetSample]
    validation: list[DatasetSample]
    test: list[DatasetSample]
    challenge: list[DatasetSample]
    groups_assigned: dict[str, str]  # group_key -> split_name
    ood_test: list[DatasetSample] = None  # type: ignore
    golden_holdout: list[DatasetSample] = None  # type: ignore
    ood_meta: OODSelectionResult | None = None

    def __post_init__(self) -> None:
        if self.ood_test is None:
            object.__setattr__(self, "ood_test", [])
        if self.golden_holdout is None:
            object.__setattr__(self, "golden_holdout", [])


class StratifiedGroupedSplitter:
    """Splits samples into isolated partitions with zero transitive leakage."""

    def __init__(
        self,
        *,
        ood_config: OODHoldoutConfig | None = None,
        historical_ood_registry: HistoricalOODRegistry | None = None,
        golden_holdout_ratio: float = 0.0,
        challenge_ratio: float = 0.05,
        enable_ood: bool = False,
    ) -> None:
        self._ood_config = ood_config or OODHoldoutConfig()
        self._ood_selector = OODPolicySelector(historical_ood_registry)
        self._golden_ratio = golden_holdout_ratio
        self._challenge_ratio = challenge_ratio
        self._enable_ood = enable_ood or (ood_config is not None)

    def split(
        self,
        samples: Sequence[DatasetSample],
        *,
        train_ratio: float = 0.70,
        validation_ratio: float = 0.15,
        test_ratio: float = 0.15,
        seed: int = 42,
    ) -> SplitResult:
        if not samples:
            return SplitResult(
                train=[],
                validation=[],
                test=[],
                challenge=[],
                groups_assigned={},
                ood_test=[],
                golden_holdout=[],
                ood_meta=None,
            )

        # 1. Build transitive connected-component leakage identities
        identities: list[LeakageIdentity] = []
        for s in samples:
            lineage = s.lineage
            inp = s.input_data
            domain = str(inp.get("domain", "") or inp.get("url", ""))
            app = str(inp.get("app", "") or inp.get("application", ""))

            identities.append(
                LeakageIdentity(
                    sample_id=s.sample_id,
                    session_id=lineage.get("source_session_id", ""),
                    episode_id=lineage.get("episode_id", ""),
                    task_id=str(lineage.get("step_index", ""))
                    if lineage.get("step_index") is not None
                    else "",
                    device_id=lineage.get("device_id", ""),
                    target_id=str(inp.get("target_id", "") or inp.get("file_path", "")),
                    target_domain=domain,
                    application_id=app,
                    strategy_lineage_id=s.strategy_lineage.get("strategy_id", ""),
                    evidence_lineage_id=s.evidence_digest,
                )
            )

        grouping = self._group_builder.compute_groups(identities)
        sample_map = {s.sample_id: s for s in samples}

        ood_groups: set[str] = set()
        ood_result = None
        if self._enable_ood:
            ood_result = self._ood_selector.select_ood_groups(
                grouping.group_attributes, self._ood_config
            )
            ood_groups = set(ood_result.selected_group_keys)

        # 2. Reserve Golden Holdout and Challenge groups from remaining
        remaining_group_keys = [
            k for k in sorted(grouping.group_to_samples.keys()) if k not in ood_groups
        ]
        rng = random.Random(seed)
        rng.shuffle(remaining_group_keys)

        golden_groups: set[str] = set()
        challenge_groups: set[str] = set()

        if self._golden_ratio > 0.0 and len(remaining_group_keys) >= 6:
            n_golden = max(1, int(len(remaining_group_keys) * self._golden_ratio))
            golden_groups = set(remaining_group_keys[:n_golden])
            remaining_group_keys = remaining_group_keys[n_golden:]

        if self._challenge_ratio > 0.0 and len(remaining_group_keys) >= 5:
            n_chal = max(1, int(len(remaining_group_keys) * self._challenge_ratio))
            challenge_groups = set(remaining_group_keys[:n_chal])
            remaining_group_keys = remaining_group_keys[n_chal:]

        # 3. Partition remaining groups into train / validation / test using stratified packing
        total_remaining = len(remaining_group_keys)
        ratio_sum = train_ratio + validation_ratio + test_ratio
        if total_remaining == 1:
            train_groups = set(remaining_group_keys)
            val_groups = set()
        elif total_remaining == 2:
            train_groups = {remaining_group_keys[0]}
            val_groups = set()
        else:
            target_train = max(1, int(round(total_remaining * (train_ratio / ratio_sum))))
            target_val = (
                max(1, int(round(total_remaining * (validation_ratio / ratio_sum))))
                if validation_ratio > 0 and total_remaining >= 4
                else (1 if total_remaining == 3 and validation_ratio > 0 else 0)
            )
            if target_train + target_val >= total_remaining:
                target_train = max(1, total_remaining - target_val - (1 if test_ratio > 0 else 0))
            train_groups = set(remaining_group_keys[:target_train])
            val_groups = set(remaining_group_keys[target_train : target_train + target_val])

        # 4. Materialize samples per split
        train_samples: list[DatasetSample] = []
        val_samples: list[DatasetSample] = []
        test_samples: list[DatasetSample] = []
        ood_samples: list[DatasetSample] = []
        golden_samples: list[DatasetSample] = []
        challenge_samples: list[DatasetSample] = []
        groups_assigned: dict[str, str] = {}

        for grp_key, sample_ids in grouping.group_to_samples.items():
            if grp_key in ood_groups:
                split_name = "ood_test"
                ood_samples.extend(sample_map[sid].with_split("ood_test") for sid in sample_ids)
            elif grp_key in golden_groups:
                split_name = "golden_holdout"
                golden_samples.extend(
                    sample_map[sid].with_split("golden_holdout") for sid in sample_ids
                )
            elif grp_key in challenge_groups:
                split_name = "challenge"
                challenge_samples.extend(
                    sample_map[sid].with_split("challenge") for sid in sample_ids
                )
            elif grp_key in train_groups:
                split_name = "train"
                train_samples.extend(sample_map[sid].with_split("train") for sid in sample_ids)
            elif grp_key in val_groups:
                split_name = "validation"
                val_samples.extend(sample_map[sid].with_split("validation") for sid in sample_ids)
            else:
                split_name = "test"
                test_samples.extend(sample_map[sid].with_split("test") for sid in sample_ids)

            groups_assigned[grp_key] = split_name

        return SplitResult(
            train=train_samples,
            validation=val_samples,
            test=test_samples,
            challenge=challenge_samples,
            groups_assigned=groups_assigned,
            ood_test=ood_samples,
            golden_holdout=golden_samples,
            ood_meta=ood_result,
        )

    @property
    def _group_builder(self) -> LeakageGroupBuilder:
        return LeakageGroupBuilder()


# Backward-compatible alias
GroupedSplitter = StratifiedGroupedSplitter
