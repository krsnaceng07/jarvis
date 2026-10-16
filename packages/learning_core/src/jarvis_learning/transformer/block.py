"""Pre-LN Transformer Block with MultiHeadAttention and FeedForward Network."""

from __future__ import annotations

from typing import Any
import numpy as np

from jarvis_learning.transformer.attention import MultiHeadAttention
from jarvis_learning.transformer.cache import KVCache
from jarvis_learning.transformer.config import TransformerConfig
from jarvis_learning.transformer.layers import PositionwiseFeedForward
from jarvis_learning.transformer.normalization import LayerNorm


class TransformerBlock:
    """Pre-LayerNorm Transformer Block."""

    def __init__(
        self,
        config: TransformerConfig,
        layer_idx: int = 0,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.config = config
        self.layer_idx = layer_idx

        self.ln1 = LayerNorm(config.d_model, eps=config.layer_norm_eps)
        self.mha = MultiHeadAttention(
            d_model=config.d_model,
            n_heads=config.n_heads,
            use_bias=config.use_bias,
            rng=rng,
        )
        self.ln2 = LayerNorm(config.d_model, eps=config.layer_norm_eps)
        self.ffn = PositionwiseFeedForward(
            d_model=config.d_model,
            d_ff=config.d_ff,
            activation=config.activation,
            use_bias=config.use_bias,
            rng=rng,
        )

        self._cache: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None = None

    def forward(
        self,
        x: np.ndarray,
        mask: np.ndarray | None = None,
        kv_cache: KVCache | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Pre-LN forward pass:

        x1 = x + MHA(LN1(x))
        x2 = x1 + FFN(LN2(x1))
        """
        norm1 = self.ln1.forward(x)
        attn_out, attn_weights = self.mha.forward(
            norm1, mask=mask, kv_cache=kv_cache, layer_idx=self.layer_idx
        )
        x1 = x + attn_out

        norm2 = self.ln2.forward(x1)
        ffn_out = self.ffn.forward(norm2)
        x2 = x1 + ffn_out

        self._cache = (x, norm1, x1, norm2)
        return x2, attn_weights

    def backward(self, grad_output: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
        """Analytical backward pass through both Pre-LN residual branches."""
        if self._cache is None:
            raise RuntimeError("Cannot call backward before forward")

        x, norm1, x1, norm2 = self._cache

        # Branch 2: x2 = x1 + FFN(norm2)
        grad_ffn_out = grad_output
        grad_x1 = grad_output.copy()

        grad_norm2, ffn_params = self.ffn.backward(grad_ffn_out)
        grad_x1_from_ln2, ln2_params = self.ln2.backward(grad_norm2)
        grad_x1 += grad_x1_from_ln2

        # Branch 1: x1 = x + MHA(norm1)
        grad_attn_out = grad_x1
        grad_x = grad_x1.copy()

        grad_norm1, mha_params = self.mha.backward(grad_attn_out)
        grad_x_from_ln1, ln1_params = self.ln1.backward(grad_norm1)
        grad_x += grad_x_from_ln1

        param_grads: dict[str, Any] = {
            "ln1": ln1_params,
            "mha": mha_params,
            "ln2": ln2_params,
            "ffn": ffn_params,
        }
        return grad_x, param_grads

    def get_weights(self, prefix: str = "") -> dict[str, np.ndarray]:
        """Extract all learnable parameters in this Transformer block."""
        weights: dict[str, np.ndarray] = {
            f"{prefix}ln1.gamma": self.ln1.gamma.copy(),
            f"{prefix}ln1.beta": self.ln1.beta.copy(),
            f"{prefix}mha.wq": self.mha.wq.copy(),
            f"{prefix}mha.wk": self.mha.wk.copy(),
            f"{prefix}mha.wv": self.mha.wv.copy(),
            f"{prefix}mha.wo": self.mha.wo.copy(),
            f"{prefix}ln2.gamma": self.ln2.gamma.copy(),
            f"{prefix}ln2.beta": self.ln2.beta.copy(),
            f"{prefix}ffn.w1": self.ffn.w1.copy(),
            f"{prefix}ffn.w2": self.ffn.w2.copy(),
        }
        if self.mha.use_bias and self.mha.bq is not None:
            weights[f"{prefix}mha.bq"] = self.mha.bq.copy()
            weights[f"{prefix}mha.bk"] = self.mha.bk.copy()
            weights[f"{prefix}mha.bv"] = self.mha.bv.copy()
            weights[f"{prefix}mha.bo"] = self.mha.bo.copy()
        if self.ffn.use_bias and self.ffn.b1 is not None:
            weights[f"{prefix}ffn.b1"] = self.ffn.b1.copy()
            weights[f"{prefix}ffn.b2"] = self.ffn.b2.copy()
        return weights

    def set_weights(self, weights: dict[str, np.ndarray], prefix: str = "") -> None:
        """Set all learnable parameters in this block with strict validation."""
        d_model = self.config.d_model
        d_ff = self.config.d_ff

        required = [
            (f"{prefix}ln1.gamma", (d_model,)),
            (f"{prefix}ln1.beta", (d_model,)),
            (f"{prefix}mha.wq", (d_model, d_model)),
            (f"{prefix}mha.wk", (d_model, d_model)),
            (f"{prefix}mha.wv", (d_model, d_model)),
            (f"{prefix}mha.wo", (d_model, d_model)),
            (f"{prefix}ln2.gamma", (d_model,)),
            (f"{prefix}ln2.beta", (d_model,)),
            (f"{prefix}ffn.w1", (d_model, d_ff)),
            (f"{prefix}ffn.w2", (d_ff, d_model)),
        ]

        if self.mha.use_bias:
            required.extend(
                [
                    (f"{prefix}mha.bq", (d_model,)),
                    (f"{prefix}mha.bk", (d_model,)),
                    (f"{prefix}mha.bv", (d_model,)),
                    (f"{prefix}mha.bo", (d_model,)),
                ]
            )
        if self.ffn.use_bias:
            required.extend(
                [
                    (f"{prefix}ffn.b1", (d_ff,)),
                    (f"{prefix}ffn.b2", (d_model,)),
                ]
            )

        for key, shape in required:
            if key not in weights:
                raise ValueError(f"Missing required block parameter: '{key}'")

        self.ln1.gamma = _validate_tensor(
            weights[f"{prefix}ln1.gamma"], (d_model,), f"{prefix}ln1.gamma"
        )
        self.ln1.beta = _validate_tensor(
            weights[f"{prefix}ln1.beta"], (d_model,), f"{prefix}ln1.beta"
        )
        self.mha.wq = _validate_tensor(
            weights[f"{prefix}mha.wq"], (d_model, d_model), f"{prefix}mha.wq"
        )
        self.mha.wk = _validate_tensor(
            weights[f"{prefix}mha.wk"], (d_model, d_model), f"{prefix}mha.wk"
        )
        self.mha.wv = _validate_tensor(
            weights[f"{prefix}mha.wv"], (d_model, d_model), f"{prefix}mha.wv"
        )
        self.mha.wo = _validate_tensor(
            weights[f"{prefix}mha.wo"], (d_model, d_model), f"{prefix}mha.wo"
        )
        self.ln2.gamma = _validate_tensor(
            weights[f"{prefix}ln2.gamma"], (d_model,), f"{prefix}ln2.gamma"
        )
        self.ln2.beta = _validate_tensor(
            weights[f"{prefix}ln2.beta"], (d_model,), f"{prefix}ln2.beta"
        )
        self.ffn.w1 = _validate_tensor(
            weights[f"{prefix}ffn.w1"], (d_model, d_ff), f"{prefix}ffn.w1"
        )
        self.ffn.w2 = _validate_tensor(
            weights[f"{prefix}ffn.w2"], (d_ff, d_model), f"{prefix}ffn.w2"
        )

        if self.mha.use_bias:
            self.mha.bq = _validate_tensor(
                weights[f"{prefix}mha.bq"], (d_model,), f"{prefix}mha.bq"
            )
            self.mha.bk = _validate_tensor(
                weights[f"{prefix}mha.bk"], (d_model,), f"{prefix}mha.bk"
            )
            self.mha.bv = _validate_tensor(
                weights[f"{prefix}mha.bv"], (d_model,), f"{prefix}mha.bv"
            )
            self.mha.bo = _validate_tensor(
                weights[f"{prefix}mha.bo"], (d_model,), f"{prefix}mha.bo"
            )

        if self.ffn.use_bias:
            self.ffn.b1 = _validate_tensor(weights[f"{prefix}ffn.b1"], (d_ff,), f"{prefix}ffn.b1")
            self.ffn.b2 = _validate_tensor(
                weights[f"{prefix}ffn.b2"], (d_model,), f"{prefix}ffn.b2"
            )


def _validate_tensor(arr: Any, expected_shape: tuple[int, ...], name: str) -> np.ndarray:
    """Validate shape, finiteness, and return float64 numpy array."""
    if not isinstance(arr, np.ndarray):
        arr = np.asarray(arr, dtype=np.float64)
    if arr.shape != expected_shape:
        raise ValueError(
            f"Shape mismatch for parameter '{name}': expected {expected_shape}, got {arr.shape}"
        )
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"Non-finite values (NaN or Inf) detected in parameter '{name}'")
    return arr.astype(np.float64)
