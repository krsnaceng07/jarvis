"""Autoregressive generation strategies and KV-cache verification."""

from __future__ import annotations

from typing import Sequence
import numpy as np

from jarvis_learning.transformer.cache import KVCache
from jarvis_learning.transformer.model import NanoTransformer


def sample_next_token(
    logits: np.ndarray,
    temperature: float = 1.0,
    top_k: int = 0,
    top_p: float = 0.0,
    repetition_penalty: float = 1.0,
    generated_tokens: Sequence[int] | None = None,
    rng: np.random.Generator | None = None,
) -> int:
    """Samples next token ID from 1D logits with sampling controls.

    Args:
        logits: (V,) unnormalized log-probabilities for the next token
        temperature: Scaling factor (<= 0 implies greedy argmax)
        top_k: If > 0, restrict sampling to top_k tokens
        top_p: If > 0.0 and < 1.0, nucleus sampling threshold
        repetition_penalty: Penalty factor applied to tokens in generated_tokens (> 1.0 penalizes)
        generated_tokens: Sequence of previous token IDs
        rng: Optional random number generator

    Returns:
        Sampled token integer index.
    """
    if rng is None:
        rng = np.random.default_rng()

    mod_logits = logits.astype(np.float64).copy()

    # Apply repetition penalty
    if repetition_penalty != 1.0 and generated_tokens:
        for tid in set(generated_tokens):
            if tid < len(mod_logits):
                if mod_logits[tid] > 0:
                    mod_logits[tid] /= repetition_penalty
                else:
                    mod_logits[tid] *= repetition_penalty

    # Greedy if temperature is tiny or zero
    if temperature <= 1e-4:
        return int(np.argmax(mod_logits))

    # Apply temperature
    mod_logits /= temperature

    # Apply Top-K filtering
    if top_k > 0 and top_k < len(mod_logits):
        indices_to_remove = np.argsort(mod_logits)[:-top_k]
        mod_logits[indices_to_remove] = -1e9

    # Softmax
    max_l = np.max(mod_logits)
    exp_l = np.exp(mod_logits - max_l)
    probs = exp_l / np.sum(exp_l)

    # Apply Top-P (Nucleus) filtering
    if 0.0 < top_p < 1.0:
        sorted_indices = np.argsort(probs)[::-1]
        sorted_probs = probs[sorted_indices]
        cumulative_probs = np.cumsum(sorted_probs)

        # Remove tokens with cumulative probability above threshold
        sorted_indices_to_remove = cumulative_probs > top_p
        # Shift to keep first token above threshold
        sorted_indices_to_remove[1:] = sorted_indices_to_remove[:-1].copy()
        sorted_indices_to_remove[0] = False

        indices_to_remove = sorted_indices[sorted_indices_to_remove]
        probs[indices_to_remove] = 0.0
        sum_p = np.sum(probs)
        if sum_p > 0:
            probs /= sum_p
        else:
            return int(sorted_indices[0])

    # Sample from multinomial
    return int(rng.choice(len(probs), p=probs))


def generate_autoregressive(
    model: NanoTransformer,
    head_projection: np.ndarray,  # (d_model, vocab_size)
    prompt_ids: np.ndarray,
    max_new_tokens: int = 20,
    temperature: float = 0.7,
    top_k: int = 40,
    top_p: float = 0.9,
    repetition_penalty: float = 1.1,
    eos_token_id: int = 2,
    use_cache: bool = True,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Generates tokens autoregressively using either full attention or KV caching."""
    if rng is None:
        rng = np.random.default_rng()

    current_ids = prompt_ids.flatten().tolist()

    if use_cache:
        # Pre-fill KV cache with prompt
        kv_cache = KVCache(model.config.n_layers)
        prompt_arr = np.array([current_ids], dtype=np.int64)
        hidden, _ = model.forward(prompt_arr, causal=True, kv_cache=kv_cache)
        last_hidden = hidden[0, -1, :]  # (d_model,)
        next_logits = last_hidden @ head_projection

        next_token = sample_next_token(
            next_logits,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
            generated_tokens=current_ids,
            rng=rng,
        )
        current_ids.append(next_token)

        for _ in range(max_new_tokens - 1):
            if next_token == eos_token_id:
                break
            # Step with 1 single token
            token_arr = np.array([[next_token]], dtype=np.int64)
            hidden, _ = model.forward(token_arr, causal=True, kv_cache=kv_cache)
            last_hidden = hidden[0, -1, :]
            next_logits = last_hidden @ head_projection

            next_token = sample_next_token(
                next_logits,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
                repetition_penalty=repetition_penalty,
                generated_tokens=current_ids,
                rng=rng,
            )
            current_ids.append(next_token)
    else:
        for _ in range(max_new_tokens):
            inp = np.array([current_ids], dtype=np.int64)
            hidden, _ = model.forward(inp, causal=True, kv_cache=None)
            last_hidden = hidden[0, -1, :]
            next_logits = last_hidden @ head_projection

            next_token = sample_next_token(
                next_logits,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
                repetition_penalty=repetition_penalty,
                generated_tokens=current_ids,
                rng=rng,
            )
            current_ids.append(next_token)
            if next_token == eos_token_id:
                break

    return np.array(current_ids, dtype=np.int64)
