"""jarvis_learning.models.memory_reranker — Model B: Memory Reranker (Shadow-Only).

Evaluates candidate memories for contextual relevance. Stays strictly
in shadow/observational mode during Wave 3 to collect causal evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifact import ModelArtifactBundle
from .base import LocalModel


@dataclass(frozen=True, slots=True)
class MemoryUsageEvidence:
    """Causal evidence tracking whether retrieved memory influenced success."""

    memory_id: str
    query: str
    retrieved: bool
    injected: bool
    explicitly_referenced: bool
    affected_decision: bool
    user_confirmed_useful: bool
    task_success_after_injection: bool
    usefulness_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "query": self.query,
            "retrieved": self.retrieved,
            "injected": self.injected,
            "explicitly_referenced": self.explicitly_referenced,
            "affected_decision": self.affected_decision,
            "user_confirmed_useful": self.user_confirmed_useful,
            "task_success_after_injection": self.task_success_after_injection,
            "usefulness_confidence": self.usefulness_confidence,
        }


class MemoryRerankerModel(LocalModel):
    """Memory reranker model. Runs in shadow mode only in Wave 3."""

    def __init__(self, model_id: str = "memory_reranker_local", version: str = "v001") -> None:
        super().__init__(target="memory_reranker", model_id=model_id, version=version)
        self.is_shadow_only = True  # Strict Wave 3 guard

    def load(self, artifact_dir: Path) -> None:
        """Load and verify reranker artifact bundle."""
        manifest, _, _, _, _ = ModelArtifactBundle.verify_and_load(
            artifact_dir, expected_target="memory_reranker"
        )
        self.version = manifest.version
        self.model_id = manifest.model_id
        self._is_loaded = True

    def score_relevance(self, query: str, memory_text: str) -> float:
        """Score semantic overlap between query and candidate memory in [0, 3]."""
        query_words = set(re.findall(r"\b\w+\b", query.lower()))
        memory_words = set(re.findall(r"\b\w+\b", memory_text.lower()))
        if not query_words or not memory_words:
            return 0.0
        overlap = len(query_words & memory_words)
        jaccard = overlap / len(query_words | memory_words)
        return round(min(3.0, jaccard * 4.0), 2)

    def predict(self, input_data: dict[str, Any]) -> dict[str, Any]:
        query = input_data.get("query", "")
        memories = input_data.get("memories", [])
        scored = [{"memory": m, "score": self.score_relevance(query, str(m))} for m in memories]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return {"ranked_memories": scored, "shadow_only": True}

    def unload(self) -> None:
        self._is_loaded = False
