import logging
import re
from datetime import datetime
from typing import Any, Dict, List

from src.plugins.memory_runtime import get_active_memory_search_manager

_log = logging.getLogger("extensions.memory_core.hybrid_search")

# For matching dates in memory/YYYY-MM-DD.md or memory/YYYY-MM-DD-slug.md
DATE_PATTERN = re.compile(r"^memory/(\d{4}-\d{2}-\d{2})")


class HybridSearchEngine:
    def __init__(self, sqlite_runtime: Any) -> None:
        self._sqlite = sqlite_runtime

    async def search(
        self,
        query: str,
        agent_id: str,
        max_results: int = 4,
        min_score: float = 0.0,
        corpus: str = "memory",
    ) -> List[Dict[str, Any]]:
        # 1. Fetch from SQLite (BM25)
        # Note: SQLite `search_text` doesn't currently filter by agent_id natively in this signature,
        # but the OpenClaw parity in `memory_core` uses a unified memory DB for the workspace.
        sqlite_candidates = self._sqlite.search_text(query, limit=max_results * 3)
        if not sqlite_candidates:
            sqlite_candidates = self._sqlite.search_substring(query, limit=max_results * 3)

        # Normalize sqlite candidates to a dict format
        hybrid_candidates: Dict[str, Dict[str, Any]] = {}

        for row in sqlite_candidates:
            key = row.get("key", "")
            # BM25 baseline score approximation
            base_score = 0.95 if query.lower() == key.lower() else 0.5

            # Extract metadata (importance) if available, otherwise default to 1.0 or 0.7
            # Note: memory_core doesn't store 'importance' yet, but lancedb does.
            # We'll treat base importance as 1.0 for FTS hits if not provided.
            hybrid_candidates[key] = {
                "key": key,
                "value": row.get("value", ""),
                "category": row.get("category", "general"),
                "base_score": base_score,
                "importance": 1.0,
                "vector_score": 0.0,
                "bm25_score": base_score,
            }

        # 2. Fetch from Vector DB (if active manager is available)
        try:
            manager = await get_active_memory_search_manager({"agentId": agent_id})
            if manager and not isinstance(manager, dict):
                vector_results = manager.search(
                    agent_id=agent_id,
                    query=query,
                    max_results=max_results * 3,
                    min_score=min_score,
                    source="memory",
                )
                for res in vector_results:
                    # In Phase 4.1, SdkMemorySearchResult has `.entry.id`, `.entry.text`, `.score`, `.entry.importance`
                    key = res.entry.id
                    if key in hybrid_candidates:
                        hybrid_candidates[key]["vector_score"] = res.score
                        hybrid_candidates[key]["base_score"] = max(
                            hybrid_candidates[key]["base_score"], res.score
                        )
                        hybrid_candidates[key]["importance"] = res.entry.importance
                    else:
                        hybrid_candidates[key] = {
                            "key": key,
                            "value": res.entry.text,
                            "category": getattr(res.entry, "category", "general"),
                            "base_score": res.score,
                            "importance": res.entry.importance,
                            "vector_score": res.score,
                            "bm25_score": 0.0,
                        }
        except Exception as e:
            _log.debug(f"Hybrid search vector retrieval failed or skipped: {e}")

        # 3. Apply Deterministic Ranking (relevance x recency x importance)
        ranked = []
        now = datetime.now()
        for key, candidate in hybrid_candidates.items():
            relevance = candidate["base_score"]
            importance = candidate.get("importance", 1.0)

            # Recency decay calculation
            recency_multiplier = 1.0
            match = DATE_PATTERN.match(key.replace("\\", "/"))
            if match:
                date_str = match.group(1)
                try:
                    entry_date = datetime.strptime(date_str, "%Y-%m-%d")
                    days_old = max(0, (now - entry_date).days)
                    # 30-day half-life decay
                    recency_multiplier = 0.5 ** (days_old / 30.0)
                except ValueError:
                    pass
            elif key.endswith("MEMORY.md") or key.endswith("USER.md"):
                recency_multiplier = 1.0  # evergreen

            # Filename boost (exact match)
            if query.lower() in key.lower():
                relevance = min(1.0, relevance + 0.2)

            final_score = relevance * recency_multiplier * importance
            candidate["final_score"] = final_score

            if final_score >= min_score:
                ranked.append(candidate)

        # Sort by final score
        ranked.sort(key=lambda x: x["final_score"], reverse=True)

        # 4. MMR Re-ranking
        mmr_results = self._mmr_reorder(ranked, query, lambda_param=0.7, top_k=max_results)

        return mmr_results

    def _mmr_reorder(
        self, candidates: List[Dict[str, Any]], query: str, lambda_param: float, top_k: int
    ) -> List[Dict[str, Any]]:
        """
        Implements Maximal Marginal Relevance (MMR) re-ordering using Jaccard similarity
        over simple token sets to penalize duplicate information.
        """
        if not candidates:
            return []

        def _tokenize(text: str) -> set:
            return set(re.findall(r"\w+", text.lower()))

        candidate_tokens = [_tokenize(c["value"]) for c in candidates]

        def _jaccard(set1: set, set2: set) -> float:
            if not set1 or not set2:
                return 0.0
            intersection = len(set1.intersection(set2))
            union = len(set1.union(set2))
            return intersection / union

        selected_indices = []
        unselected_indices = list(range(len(candidates)))

        while len(selected_indices) < top_k and unselected_indices:
            best_idx = -1
            best_mmr_score = -float("inf")

            for idx in unselected_indices:
                # Relevance is the already-calculated final_score (normalized roughly 0 to 1)
                rel = candidates[idx]["final_score"]

                # Max similarity to already selected candidates
                max_sim = 0.0
                for sel_idx in selected_indices:
                    sim = _jaccard(candidate_tokens[idx], candidate_tokens[sel_idx])
                    max_sim = max(max_sim, sim)

                mmr_score = lambda_param * rel - (1 - lambda_param) * max_sim

                if mmr_score > best_mmr_score:
                    best_mmr_score = mmr_score
                    best_idx = idx

            if best_idx != -1:
                selected_indices.append(best_idx)
                unselected_indices.remove(best_idx)
            else:
                break

        return [candidates[i] for i in selected_indices]
