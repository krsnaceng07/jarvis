"""jarvis_learning.datasets.leakage_groups — transitive connected-component grouping.

Uses Disjoint-Set (Union-Find) to compute connected components across samples
that share any leakage-sensitive identity attribute.
If Sample A shares domain with Sample B, and Sample B shares device with Sample C,
then A, B, and C belong to the exact same atomic leakage group.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True, slots=True)
class LeakageIdentity:
    """Multi-dimensional leakage attributes for a dataset sample."""

    sample_id: str
    session_id: str = ""
    episode_id: str = ""
    task_id: str = ""
    device_id: str = ""
    target_id: str = ""
    target_domain: str = ""
    application_id: str = ""
    tool_category: str = ""
    strategy_lineage_id: str = ""
    evidence_lineage_id: str = ""

    def non_empty_attributes(self) -> list[str]:
        """Return list of attribute tags for graph edge creation."""
        tags = []
        if self.session_id:
            tags.append(f"sess:{self.session_id}")
        if self.episode_id:
            tags.append(f"ep:{self.episode_id}")
        if self.task_id:
            tags.append(f"task:{self.task_id}")
        if self.device_id:
            tags.append(f"dev:{self.device_id}")
        if self.target_id:
            tags.append(f"tgt:{self.target_id}")
        if self.target_domain:
            tags.append(f"dom:{self.target_domain.lower().strip()}")
        if self.application_id:
            tags.append(f"app:{self.application_id.lower().strip()}")
        if self.strategy_lineage_id:
            tags.append(f"strat:{self.strategy_lineage_id}")
        if self.evidence_lineage_id:
            tags.append(f"ev:{self.evidence_lineage_id}")
        return tags


class DisjointSet:
    """Classic Union-Find data structure with path compression and rank heuristic."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = {}

    def find(self, item: str) -> str:
        if item not in self._parent:
            self._parent[item] = item
            self._rank[item] = 0
            return item
        if self._parent[item] != item:
            self._parent[item] = self.find(self._parent[item])
        return self._parent[item]

    def union(self, item1: str, item2: str) -> None:
        root1 = self.find(item1)
        root2 = self.find(item2)
        if root1 == root2:
            return

        # Union by rank
        if self._rank[root1] < self._rank[root2]:
            self._parent[root1] = root2
        elif self._rank[root1] > self._rank[root2]:
            self._parent[root2] = root1
        else:
            self._parent[root2] = root1
            self._rank[root1] += 1


@dataclass
class LeakageGroupingResult:
    """Result of transitive connected-component grouping."""

    sample_to_group: dict[str, str] = field(default_factory=dict)
    group_to_samples: dict[str, list[str]] = field(default_factory=dict)
    group_attributes: dict[str, set[str]] = field(default_factory=dict)


class LeakageGroupBuilder:
    """Builds transitive connected components for samples."""

    def compute_groups(self, identities: Iterable[LeakageIdentity]) -> LeakageGroupingResult:
        uf = DisjointSet()
        attr_to_first_sample: dict[str, str] = {}
        sample_identities: dict[str, LeakageIdentity] = {}

        # 1. Connect samples via shared attributes
        for ident in identities:
            sample_identities[ident.sample_id] = ident
            # Ensure sample exists in UF
            uf.find(ident.sample_id)

            for attr in ident.non_empty_attributes():
                if attr in attr_to_first_sample:
                    # Union this sample with previous sample sharing the attribute
                    uf.union(ident.sample_id, attr_to_first_sample[attr])
                else:
                    attr_to_first_sample[attr] = ident.sample_id

        # 2. Extract final connected components
        sample_to_group: dict[str, str] = {}
        group_to_samples: dict[str, list[str]] = {}
        group_attributes: dict[str, set[str]] = {}

        for sample_id, ident in sample_identities.items():
            root = uf.find(sample_id)
            group_key = f"grp_{root}"
            sample_to_group[sample_id] = group_key
            group_to_samples.setdefault(group_key, []).append(sample_id)
            group_attributes.setdefault(group_key, set()).update(ident.non_empty_attributes())

        return LeakageGroupingResult(
            sample_to_group=sample_to_group,
            group_to_samples=group_to_samples,
            group_attributes=group_attributes,
        )
