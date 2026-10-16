"""Configuration for NanoTransformer architecture with dimension validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from jarvis_learning.transformer.errors import DimensionMismatchError


@dataclass(frozen=True, slots=True)
class TransformerConfig:
    """Hyperparameter configuration for NanoTransformer.

    Default parameters are tuned for fast, inspectable CPU training and inference
    on standard developer hardware (e.g. Intel Core i5).
    """

    vocab_size: int = 260
    max_seq_len: int = 128
    d_model: int = 64
    n_heads: int = 4
    d_ff: int = 256
    n_layers: int = 2
    dropout: float = 0.0
    layer_norm_eps: float = 1e-5
    positional_encoding: str = "sinusoidal"  # 'sinusoidal' or 'learned'
    activation: str = "gelu"  # 'gelu' or 'relu'
    use_bias: bool = True

    def __post_init__(self) -> None:
        if self.vocab_size <= 0:
            raise DimensionMismatchError(f"vocab_size must be positive, got {self.vocab_size}")
        if self.max_seq_len <= 0:
            raise DimensionMismatchError(f"max_seq_len must be positive, got {self.max_seq_len}")
        if self.d_model <= 0:
            raise DimensionMismatchError(f"d_model must be positive, got {self.d_model}")
        if self.n_heads <= 0:
            raise DimensionMismatchError(f"n_heads must be positive, got {self.n_heads}")
        if self.d_model % self.n_heads != 0:
            raise DimensionMismatchError(
                f"d_model ({self.d_model}) must be divisible by n_heads ({self.n_heads})"
            )
        if self.d_ff <= 0:
            raise DimensionMismatchError(f"d_ff must be positive, got {self.d_ff}")
        if self.n_layers <= 0:
            raise DimensionMismatchError(f"n_layers must be positive, got {self.n_layers}")
        if not (0.0 <= self.dropout < 1.0):
            raise DimensionMismatchError(f"dropout must be in [0, 1), got {self.dropout}")
        if self.positional_encoding not in ("sinusoidal", "learned"):
            raise DimensionMismatchError(
                f"positional_encoding must be 'sinusoidal' or 'learned', got {self.positional_encoding}"
            )
        if self.activation not in ("gelu", "relu"):
            raise DimensionMismatchError(
                f"activation must be 'gelu' or 'relu', got {self.activation}"
            )

    @property
    def d_head(self) -> int:
        return self.d_model // self.n_heads

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TransformerConfig:
        return cls(
            vocab_size=int(data.get("vocab_size", 260)),
            max_seq_len=int(data.get("max_seq_len", 128)),
            d_model=int(data.get("d_model", 64)),
            n_heads=int(data.get("n_heads", 4)),
            d_ff=int(data.get("d_ff", 256)),
            n_layers=int(data.get("n_layers", 2)),
            dropout=float(data.get("dropout", 0.0)),
            layer_norm_eps=float(data.get("layer_norm_eps", 1e-5)),
            positional_encoding=str(data.get("positional_encoding", "sinusoidal")),
            activation=str(data.get("activation", "gelu")),
            use_bias=bool(data.get("use_bias", True)),
        )
