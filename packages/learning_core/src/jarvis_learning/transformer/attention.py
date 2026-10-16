"""Multi-Head Attention and Scaled Dot-Product Attention with KV caching."""

from __future__ import annotations

import numpy as np

from jarvis_learning.transformer.cache import KVCache


class ScaledDotProductAttention:
    """Scaled Dot-Product Attention with exact analytical gradients."""

    def __init__(self, d_k: int) -> None:
        self.d_k = d_k
        self.scale = 1.0 / np.sqrt(d_k)
        self._cache: (
            tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray | None] | None
        ) = None

    def forward(
        self,
        q: np.ndarray,
        k: np.ndarray,
        v: np.ndarray,
        mask: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Forward pass.

        Args:
            q: (B, H, T_q, d_k)
            k: (B, H, T_k, d_k)
            v: (B, H, T_k, d_v)
            mask: Optional boolean or float mask broadcastable to (B, H, T_q, T_k)
                  True/1 means keep, False/0 means mask out.
        """
        scores = (q @ np.swapaxes(k, -1, -2)) * self.scale

        if mask is not None:
            scores = np.where(mask, scores, -1e9)

        scores_max = np.max(scores, axis=-1, keepdims=True)
        exp_scores = np.exp(scores - scores_max)
        if mask is not None:
            exp_scores = np.where(mask, exp_scores, 0.0)

        sum_exp = np.sum(exp_scores, axis=-1, keepdims=True)
        attn_weights = np.where(sum_exp > 0, exp_scores / np.maximum(sum_exp, 1e-12), 0.0)

        output = attn_weights @ v
        self._cache = (q, k, v, attn_weights, mask)
        return output, attn_weights

    def backward(self, grad_output: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Analytical gradient calculation for Scaled Dot-Product Attention.

        Returns:
            (grad_q, grad_k, grad_v)
        """
        if self._cache is None:
            raise RuntimeError("Cannot call backward before forward")

        q, k, v, attn_weights, mask = self._cache

        grad_v = np.swapaxes(attn_weights, -1, -2) @ grad_output
        grad_attn_weights = grad_output @ np.swapaxes(v, -1, -2)

        sum_grad_times_weights = np.sum(grad_attn_weights * attn_weights, axis=-1, keepdims=True)
        grad_scores = attn_weights * (grad_attn_weights - sum_grad_times_weights)

        if mask is not None:
            grad_scores = np.where(mask, grad_scores, 0.0)

        grad_q = (grad_scores @ k) * self.scale
        grad_k = (np.swapaxes(grad_scores, -1, -2) @ q) * self.scale

        return grad_q, grad_k, grad_v


class MultiHeadAttention:
    """Multi-Head Attention supporting linear projections, KV-caching, and backpropagation."""

    def __init__(
        self,
        d_model: int,
        n_heads: int,
        use_bias: bool = True,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.d_model = d_model
        self.n_heads = n_heads
        self.d_k = d_model // n_heads
        self.use_bias = use_bias
        if rng is None:
            rng = np.random.default_rng()

        std = 1.0 / np.sqrt(d_model)
        self.wq = rng.normal(0.0, std, size=(d_model, d_model)).astype(np.float64)
        self.wk = rng.normal(0.0, std, size=(d_model, d_model)).astype(np.float64)
        self.wv = rng.normal(0.0, std, size=(d_model, d_model)).astype(np.float64)
        self.wo = rng.normal(0.0, std, size=(d_model, d_model)).astype(np.float64)

        self.bq = np.zeros((d_model,), dtype=np.float64) if use_bias else None
        self.bk = np.zeros((d_model,), dtype=np.float64) if use_bias else None
        self.bv = np.zeros((d_model,), dtype=np.float64) if use_bias else None
        self.bo = np.zeros((d_model,), dtype=np.float64) if use_bias else None

        self.dot_product = ScaledDotProductAttention(self.d_k)
        self._cache: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None = None

    def _split_heads(self, x: np.ndarray) -> np.ndarray:
        b, t, _ = x.shape
        return x.reshape(b, t, self.n_heads, self.d_k).swapaxes(1, 2)

    def _combine_heads(self, x: np.ndarray) -> np.ndarray:
        b, _, t, _ = x.shape
        return x.swapaxes(1, 2).reshape(b, t, self.d_model)

    def forward(
        self,
        x: np.ndarray,
        mask: np.ndarray | None = None,
        kv_cache: KVCache | None = None,
        layer_idx: int = 0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Forward pass with optional KV cache."""
        b, t, _ = x.shape

        q = x @ self.wq
        k = x @ self.wk
        v = x @ self.wv
        if self.bq is not None:
            q += self.bq
        if self.bk is not None:
            k += self.bk
        if self.bv is not None:
            v += self.bv

        q = self._split_heads(q)
        k = self._split_heads(k)
        v = self._split_heads(v)

        if kv_cache is not None:
            k, v = kv_cache.update(layer_idx, k, v)

        attn_out, attn_weights = self.dot_product.forward(q, k, v, mask=mask)
        combined = self._combine_heads(attn_out)

        out = combined @ self.wo
        if self.bo is not None:
            out += self.bo

        self._cache = (x, q, k, v, combined)
        return out, attn_weights

    def backward(self, grad_output: np.ndarray) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """Analytical backward pass."""
        if self._cache is None:
            raise RuntimeError("Cannot call backward before forward")

        x, q, k, v, combined = self._cache
        b, t, _ = x.shape

        grad_params: dict[str, np.ndarray] = {}

        grad_wo = combined.reshape(-1, self.d_model).T @ grad_output.reshape(-1, self.d_model)
        grad_params["wo"] = grad_wo
        if self.bo is not None:
            grad_params["bo"] = np.sum(grad_output, axis=tuple(range(grad_output.ndim - 1)))

        grad_combined = grad_output @ self.wo.T
        grad_attn_out = self._split_heads(grad_combined)

        grad_q, grad_k, grad_v = self.dot_product.backward(grad_attn_out)

        grad_q = self._combine_heads(grad_q)
        grad_k = self._combine_heads(grad_k)
        grad_v = self._combine_heads(grad_v)

        grad_wq = x.reshape(-1, self.d_model).T @ grad_q.reshape(-1, self.d_model)
        grad_wk = x.reshape(-1, self.d_model).T @ grad_k.reshape(-1, self.d_model)
        grad_wv = x.reshape(-1, self.d_model).T @ grad_v.reshape(-1, self.d_model)

        grad_params["wq"] = grad_wq
        grad_params["wk"] = grad_wk
        grad_params["wv"] = grad_wv

        if self.bq is not None:
            grad_params["bq"] = np.sum(grad_q, axis=tuple(range(grad_q.ndim - 1)))
        if self.bk is not None:
            grad_params["bk"] = np.sum(grad_k, axis=tuple(range(grad_k.ndim - 1)))
        if self.bv is not None:
            grad_params["bv"] = np.sum(grad_v, axis=tuple(range(grad_v.ndim - 1)))

        grad_x = (grad_q @ self.wq.T) + (grad_k @ self.wk.T) + (grad_v @ self.wv.T)
        return grad_x, grad_params


def create_causal_mask(seq_len: int) -> np.ndarray:
    """Returns causal triangular mask of shape (1, 1, seq_len, seq_len).

    1/True indicates allowed attention (j <= i), 0/False indicates future position.
    """
    return np.tril(np.ones((1, 1, seq_len, seq_len), dtype=bool))
