"""Hardware resource estimation and pre-training budget enforcement."""

from __future__ import annotations

from dataclasses import dataclass

from jarvis_learning.transformer.config import TransformerConfig
from jarvis_learning.transformer.errors import ResourceBudgetExceededError


@dataclass(frozen=True, slots=True)
class ResourceEstimate:
    """Estimated resource footprint for training/inference."""

    total_parameters: int
    weights_memory_bytes: int
    optimizer_memory_bytes: int
    gradients_memory_bytes: int
    estimated_activation_bytes: int
    total_training_memory_bytes: int


class ResourceEstimator:
    """Calculates exact parameter counts and memory requirements."""

    @staticmethod
    def estimate(
        config: TransformerConfig,
        batch_size: int = 16,
        seq_len: int = 64,
        dtype_bytes: int = 8,  # float64 = 8 bytes
    ) -> ResourceEstimate:
        """Calculates parameters and memory requirements."""
        # 1. Embeddings
        tok_params = config.vocab_size * config.d_model
        pos_params = (
            config.max_seq_len * config.d_model if config.positional_encoding == "learned" else 0
        )

        # 2. Blocks
        d_m = config.d_model
        d_ff = config.d_ff
        bias_m = d_m if config.use_bias else 0
        bias_ff = d_ff if config.use_bias else 0

        ln_params = 2 * d_m  # gamma + beta
        mha_params = 4 * (d_m * d_m + bias_m)  # wq, wk, wv, wo + biases
        ffn_params = (d_m * d_ff + bias_ff) + (d_ff * d_m + bias_m)

        block_params = ln_params + mha_params + ln_params + ffn_params
        total_block_params = config.n_layers * block_params

        # 3. Final LN
        final_ln_params = 2 * d_m

        total_params = tok_params + pos_params + total_block_params + final_ln_params

        weights_bytes = total_params * dtype_bytes
        # AdamW stores 1st and 2nd moments
        opt_bytes = 2 * total_params * dtype_bytes
        grad_bytes = total_params * dtype_bytes

        # Activations roughly B * T * d_model * (layers * factor)
        act_elements = batch_size * seq_len * d_m * (config.n_layers * 12)
        act_bytes = act_elements * dtype_bytes

        total_training_bytes = weights_bytes + opt_bytes + grad_bytes + act_bytes

        return ResourceEstimate(
            total_parameters=total_params,
            weights_memory_bytes=weights_bytes,
            optimizer_memory_bytes=opt_bytes,
            gradients_memory_bytes=grad_bytes,
            estimated_activation_bytes=act_bytes,
            total_training_memory_bytes=total_training_bytes,
        )

    @staticmethod
    def validate_budget(
        config: TransformerConfig,
        max_parameters: int = 10_000_000,
        max_ram_bytes: int = 1_000_000_000,  # 1 GB
        batch_size: int = 16,
        seq_len: int = 64,
    ) -> ResourceEstimate:
        """Validates that configuration fits within allowable hardware limits."""
        est = ResourceEstimator.estimate(config, batch_size=batch_size, seq_len=seq_len)
        if est.total_parameters > max_parameters:
            raise ResourceBudgetExceededError(
                f"Model parameters {est.total_parameters:,} exceeds budget {max_parameters:,}"
            )
        if est.total_training_memory_bytes > max_ram_bytes:
            raise ResourceBudgetExceededError(
                f"Required memory {est.total_training_memory_bytes / 1e6:.1f} MB exceeds budget {max_ram_bytes / 1e6:.1f} MB"
            )
        return est
