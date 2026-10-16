"""jarvis_learning.datasets.deduplicator — operational contrast-preserving deduplication.

Enforces:
- 4 deduplication tiers: EXACT_DUPLICATE, CANONICAL_DUPLICATE, NEAR_DUPLICATE,
  SEMANTIC_SIMILAR_BUT_OPERATIONALLY_DISTINCT.
- Contrast preservation: samples with contrasting outcomes (optimal vs acceptable vs failure)
  are NEVER collapsed against each other by token similarity.
- Bounded O(n) task-key deduplication keeping representative diversity.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from .canonicalization import canonical_hash
from .schema import DatasetSample


@dataclass(frozen=True, slots=True)
class DeduplicationResult:
    """Result of the operational deduplication pipeline."""

    unique_samples: list[DatasetSample]
    exact_dupes_removed: int
    canonical_dupes_removed: int
    near_token_dupes_removed: int
    task_key_dupes_removed: int
    contrastive_pairs_kept: int = 0

    @property
    def token_dupes_removed(self) -> int:
        """Backward-compatible alias for near_token_dupes_removed."""
        return self.near_token_dupes_removed

    @property
    def total_removed(self) -> int:
        return (
            self.exact_dupes_removed
            + self.canonical_dupes_removed
            + self.near_token_dupes_removed
            + self.task_key_dupes_removed
        )


def _exact_content_hash(sample: DatasetSample) -> str:
    raw = json.dumps({"input": sample.input_data, "label": sample.label}, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _canonical_payload_hash(sample: DatasetSample) -> str:
    return canonical_hash({"input": sample.input_data, "label": sample.label})


def _normalize_text_tokens(text: str) -> set[str]:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return set(text.split())


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union > 0 else 0.0


def _operational_signature(sample: DatasetSample) -> str:
    tool = sample.label.get("tool", "")
    is_neg = sample.label.get("is_negative", False)
    quality = sample.label_quality
    app = sample.lineage.get("source_agent_id", "") or sample.input_data.get("app", "")
    causal_type = sample.causal_attribution.get("causal_failure_type", "")
    return f"{tool}|{is_neg}|{quality}|{app}|{causal_type}"


def _task_key(sample: DatasetSample) -> str:
    """Extract a task-level grouping key for deduplication."""
    user_input = sample.input_data.get("user_input", "")
    prefix = re.sub(r"[^\w\s]", "", user_input.lower())[:50].strip()
    tool = sample.label.get("tool", "")
    is_negative = sample.label.get("is_negative", False)
    quality = sample.label_quality
    return f"{prefix}|{tool}|{is_negative}|{quality}"


class DatasetDeduplicator:
    """Operational deduplicator preserving critical failure/success contrasts."""

    def __init__(
        self,
        *,
        token_similarity_threshold: float = 0.85,
    ) -> None:
        self._token_threshold = token_similarity_threshold

    def deduplicate(self, samples: list[DatasetSample]) -> DeduplicationResult:
        t1_samples, exact_removed = self._exact_dedup(samples)
        t2_samples, canonical_removed = self._canonical_dedup(t1_samples)
        t3_samples, near_removed = self._near_token_dedup(t2_samples)
        t4_samples, task_removed = self._task_key_dedup(t3_samples)

        # Count preserved contrastive pairs (same text prefix with differing outcome)
        prefixes: dict[str, set[str]] = {}
        for s in t4_samples:
            p = re.sub(r"[^\w\s]", "", s.input_data.get("user_input", "").lower())[:50].strip()
            outcome = (
                "neg"
                if s.label.get("is_negative", False) or s.label_quality in ("wrong", "unsafe")
                else "pos"
            )
            prefixes.setdefault(p, set()).add(outcome)
        contrast_count = sum(1 for outs in prefixes.values() if len(outs) > 1)

        return DeduplicationResult(
            unique_samples=t4_samples,
            exact_dupes_removed=exact_removed,
            canonical_dupes_removed=canonical_removed,
            near_token_dupes_removed=near_removed,
            task_key_dupes_removed=task_removed,
            contrastive_pairs_kept=contrast_count,
        )

    def _exact_dedup(self, samples: list[DatasetSample]) -> tuple[list[DatasetSample], int]:
        seen: set[str] = set()
        unique: list[DatasetSample] = []
        removed = 0
        for s in samples:
            h = _exact_content_hash(s)
            if h in seen:
                removed += 1
            else:
                seen.add(h)
                unique.append(s)
        return unique, removed

    def _canonical_dedup(self, samples: list[DatasetSample]) -> tuple[list[DatasetSample], int]:
        seen: set[str] = set()
        unique: list[DatasetSample] = []
        removed = 0
        for s in samples:
            h = _canonical_payload_hash(s)
            if h in seen:
                removed += 1
            else:
                seen.add(h)
                unique.append(s)
        return unique, removed

    def _near_token_dedup(self, samples: list[DatasetSample]) -> tuple[list[DatasetSample], int]:
        if len(samples) <= 1:
            return samples, 0

        token_sets: list[set[str]] = []
        op_sigs: list[str] = []
        for s in samples:
            txt = s.input_data.get("user_input", "")
            token_sets.append(_normalize_text_tokens(txt) if isinstance(txt, str) else set())
            op_sigs.append(_operational_signature(s))

        keep = [True] * len(samples)
        removed = 0

        for i in range(len(samples)):
            if not keep[i]:
                continue
            for j in range(i + 1, len(samples)):
                if not keep[j]:
                    continue
                if samples[i].target != samples[j].target:
                    continue

                # Contrast preservation: only collapse if operational outcome signatures match
                if op_sigs[i] != op_sigs[j]:
                    continue

                sim = _jaccard_similarity(token_sets[i], token_sets[j])
                if sim >= self._token_threshold:
                    if samples[j].quality_score > samples[i].quality_score:
                        keep[i] = False
                        removed += 1
                        break
                    else:
                        keep[j] = False
                        removed += 1

        unique = [s for s, k in zip(samples, keep) if k]
        return unique, removed

    def _task_key_dedup(self, samples: list[DatasetSample]) -> tuple[list[DatasetSample], int]:
        groups: dict[str, list[DatasetSample]] = {}
        for s in samples:
            key = _task_key(s)
            groups.setdefault(key, []).append(s)

        unique: list[DatasetSample] = []
        removed = 0

        for key, group in groups.items():
            if len(group) == 1:
                unique.append(group[0])
            else:
                group.sort(
                    key=lambda s: (s.quality_score, s.label_confidence),
                    reverse=True,
                )
                unique.append(group[0])
                removed += len(group) - 1

        return unique, removed
