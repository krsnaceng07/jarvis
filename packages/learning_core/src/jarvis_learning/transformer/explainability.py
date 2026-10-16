"""Attention rollout and token importance attribution for NanoTransformer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
import numpy as np

from jarvis_learning.transformer.tokenizer import BaseTokenizer


@dataclass(frozen=True, slots=True)
class TokenAttribution:
    """Attribution score for a single token."""

    token_id: int
    token_str: str
    attribution_mass: float


class AttentionExplainer:
    """Computes attention rollout and token importance across transformer layers."""

    @staticmethod
    def compute_rollout(attentions: Sequence[np.ndarray]) -> np.ndarray:
        """Computes attention rollout across all transformer layers.

        Formula:
            A_rollout = A_L @ A_{L-1} @ ... @ A_1 (with residual identity added)

        Args:
            attentions: List of attention matrices per layer, shape (B, H, T, T)

        Returns:
            Rollout matrix of shape (B, T, T)
        """
        if not attentions:
            raise ValueError("Attentions list cannot be empty")

        b, h, t, _ = attentions[0].shape
        eye = np.eye(t, dtype=np.float64)[np.newaxis, :, :]  # (1, T, T)

        # Average over attention heads
        rollout = np.eye(t, dtype=np.float64)[np.newaxis, :, :]
        rollout = np.repeat(rollout, b, axis=0)

        for attn in attentions:
            # Average over heads: (B, T, T)
            avg_attn = np.mean(attn, axis=1)
            # Add identity for residual connection and normalize rows
            a_res = 0.5 * avg_attn + 0.5 * eye
            row_sums = np.sum(a_res, axis=-1, keepdims=True)
            a_norm = a_res / np.maximum(row_sums, 1e-12)
            rollout = rollout @ a_norm

        return rollout

    @staticmethod
    def attribute_tokens(
        input_ids: np.ndarray,
        attentions: Sequence[np.ndarray],
        tokenizer: BaseTokenizer,
        target_token_pos: int = -1,
    ) -> list[TokenAttribution]:
        """Attributes attention mass to input tokens for a specific query token position."""
        rollout = AttentionExplainer.compute_rollout(attentions)
        # Take batch 0, target position
        t_pos = target_token_pos if target_token_pos >= 0 else rollout.shape[1] - 1
        masses = rollout[0, t_pos, :]  # Shape: (T,)

        # Normalize masses
        sum_mass = float(np.sum(masses))
        if sum_mass > 0:
            masses = masses / sum_mass

        tokens = input_ids[0] if input_ids.ndim == 2 else input_ids
        attributions: list[TokenAttribution] = []

        for tid, m in zip(tokens, masses):
            tok_str = tokenizer.decode([tid], strip_special=False)
            attributions.append(
                TokenAttribution(token_id=int(tid), token_str=tok_str, attribution_mass=float(m))
            )

        return sorted(attributions, key=lambda a: a.attribution_mass, reverse=True)
