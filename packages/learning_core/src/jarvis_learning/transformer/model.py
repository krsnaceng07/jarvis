"""NanoTransformer base architecture trunk."""

from __future__ import annotations

from typing import Any
import numpy as np

from jarvis_learning.transformer.attention import create_causal_mask
from jarvis_learning.transformer.block import TransformerBlock
from jarvis_learning.transformer.cache import KVCache
from jarvis_learning.transformer.config import TransformerConfig
from jarvis_learning.transformer.embeddings import (
    LearnedPositionalEncoding,
    SinusoidalPositionalEncoding,
    TokenEmbedding,
)
from jarvis_learning.transformer.normalization import LayerNorm


class NanoTransformer:
    """NanoTransformer base trunk model.

    Accepts token IDs, applies embeddings, positional encoding, N TransformerBlocks,
    and a final LayerNorm. Returns hidden representations H of shape (B, T, d_model).
    """

    def __init__(
        self,
        config: TransformerConfig,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.config = config
        if rng is None:
            rng = np.random.default_rng()
        self.rng = rng

        self.token_embedding = TokenEmbedding(config.vocab_size, config.d_model, rng=rng)

        if config.positional_encoding == "learned":
            self.pos_encoding = LearnedPositionalEncoding(
                config.max_seq_len, config.d_model, rng=rng
            )
        else:
            self.pos_encoding = SinusoidalPositionalEncoding(config.max_seq_len, config.d_model)

        self.blocks = [
            TransformerBlock(config=config, layer_idx=i, rng=rng) for i in range(config.n_layers)
        ]
        self.final_ln = LayerNorm(config.d_model, eps=config.layer_norm_eps)

        self._cache: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None

    def forward(
        self,
        input_ids: np.ndarray,
        padding_mask: np.ndarray | None = None,
        causal: bool = True,
        kv_cache: KVCache | None = None,
    ) -> tuple[np.ndarray, list[np.ndarray]]:
        """Forward pass through the transformer trunk.

        Args:
            input_ids: (B, T) int64 token array
            padding_mask: Optional boolean mask (B, T) where True=keep, False=pad
            causal: Whether to apply autoregressive causal masking
            kv_cache: Optional KVCache for incremental decoding

        Returns:
            hidden_states: (B, T, d_model)
            attentions: list of attention weight tensors per layer
        """
        b, t = input_ids.shape
        tok_emb = self.token_embedding.forward(input_ids)

        # Handle KV cache sequence position
        if kv_cache is not None and kv_cache.current_seq_len > 0:
            past_len = kv_cache.current_seq_len
            pos_emb = self.pos_encoding.forward(past_len + t)[:, past_len : past_len + t, :]
        else:
            pos_emb = self.pos_encoding.forward(t)

        x = tok_emb + pos_emb

        # Combine causal and padding masks
        mask: np.ndarray | None = None
        if causal:
            c_mask = create_causal_mask(t)  # (1, 1, t, t)
            mask = c_mask
        if padding_mask is not None:
            # padding_mask shape: (B, T) -> expand to (B, 1, 1, T)
            p_mask = padding_mask[:, np.newaxis, np.newaxis, :]
            mask = p_mask if mask is None else (mask & p_mask)

        layer_attns: list[np.ndarray] = []
        for block in self.blocks:
            x, attn = block.forward(x, mask=mask, kv_cache=kv_cache)
            layer_attns.append(attn)

        hidden_states = self.final_ln.forward(x)
        self._cache = (input_ids, x, hidden_states)
        return hidden_states, layer_attns

    def backward(self, grad_hidden_states: np.ndarray) -> dict[str, Any]:
        """Analytical backward pass from hidden states down to token embeddings."""
        if self._cache is None:
            raise RuntimeError("Cannot call backward before forward")

        input_ids, pre_ln_x, hidden_states = self._cache

        grad_x, final_ln_params = self.final_ln.backward(grad_hidden_states)

        block_grads: list[dict[str, Any]] = []
        for block in reversed(self.blocks):
            grad_x, b_params = block.backward(grad_x)
            block_grads.insert(0, b_params)

        grad_tok = self.token_embedding.backward(grad_x)

        grads: dict[str, Any] = {
            "token_embedding": grad_tok,
            "blocks": block_grads,
            "final_ln": final_ln_params,
        }

        if self.config.positional_encoding == "learned":
            b, t = input_ids.shape
            pos_grad = self.pos_encoding.backward(grad_x)
            grads["pos_encoding"] = pos_grad

        return grads

    def get_weights(self) -> dict[str, np.ndarray]:
        """Extract all learnable parameters in the entire Transformer trunk."""
        weights: dict[str, np.ndarray] = {
            "token_embedding.weight": self.token_embedding.weight.copy(),
            "final_ln.gamma": self.final_ln.gamma.copy(),
            "final_ln.beta": self.final_ln.beta.copy(),
        }
        if self.config.positional_encoding == "learned" and hasattr(self.pos_encoding, "weight"):
            weights["pos_encoding.weight"] = self.pos_encoding.weight.copy()

        for i, block in enumerate(self.blocks):
            block_weights = block.get_weights(prefix=f"blocks.{i}.")
            weights.update(block_weights)

        return weights

    def set_weights(self, weights: dict[str, np.ndarray]) -> None:
        """Restore all parameters in the trunk with strict validation."""
        from jarvis_learning.transformer.block import _validate_tensor

        if "token_embedding.weight" not in weights:
            raise ValueError("Missing parameter: 'token_embedding.weight'")
        self.token_embedding.weight = _validate_tensor(
            weights["token_embedding.weight"],
            (self.config.vocab_size, self.config.d_model),
            "token_embedding.weight",
        )

        if "final_ln.gamma" not in weights or "final_ln.beta" not in weights:
            raise ValueError("Missing parameter: 'final_ln.gamma' or 'final_ln.beta'")
        self.final_ln.gamma = _validate_tensor(
            weights["final_ln.gamma"], (self.config.d_model,), "final_ln.gamma"
        )
        self.final_ln.beta = _validate_tensor(
            weights["final_ln.beta"], (self.config.d_model,), "final_ln.beta"
        )

        if self.config.positional_encoding == "learned" and hasattr(self.pos_encoding, "weight"):
            if "pos_encoding.weight" not in weights:
                raise ValueError("Missing parameter: 'pos_encoding.weight'")
            self.pos_encoding.weight = _validate_tensor(
                weights["pos_encoding.weight"],
                (self.config.max_seq_len, self.config.d_model),
                "pos_encoding.weight",
            )

        for i, block in enumerate(self.blocks):
            block.set_weights(weights, prefix=f"blocks.{i}.")
