"""JARVIS Transformer Laboratory and Engine."""

from __future__ import annotations

from jarvis_learning.transformer.abstention import AbstentionConfig, AbstentionDecision
from jarvis_learning.transformer.attention import MultiHeadAttention, ScaledDotProductAttention
from jarvis_learning.transformer.block import TransformerBlock
from jarvis_learning.transformer.cache import KVCache
from jarvis_learning.transformer.checkpoint import (
    CheckpointMetadata,
    load_checkpoint,
    save_checkpoint,
)
from jarvis_learning.transformer.config import TransformerConfig
from jarvis_learning.transformer.dataset_adapter import BatchTensors, DatasetAdapter
from jarvis_learning.transformer.embeddings import (
    LearnedPositionalEncoding,
    SinusoidalPositionalEncoding,
    TokenEmbedding,
)
from jarvis_learning.transformer.errors import (
    AbstentionTriggered,
    CheckpointCompatibilityError,
    DimensionMismatchError,
    GradientCheckFailedError,
    ResourceBudgetExceededError,
    TokenizerError,
    TransformerError,
)
from jarvis_learning.transformer.explainability import AttentionExplainer, TokenAttribution
from jarvis_learning.transformer.generation import generate_autoregressive, sample_next_token
from jarvis_learning.transformer.gradient_check import check_gradients
from jarvis_learning.transformer.gradients import clip_grad_norm, compute_grad_norm, scale_gradients
from jarvis_learning.transformer.heads import (
    CausalLMHead,
    LastValidTokenPooling,
    OutcomePredictionHead,
    ToolClassificationHead,
)
from jarvis_learning.transformer.layers import PositionwiseFeedForward, gelu, gelu_prime
from jarvis_learning.transformer.loss import CrossEntropyLoss
from jarvis_learning.transformer.model import NanoTransformer
from jarvis_learning.transformer.normalization import LayerNorm
from jarvis_learning.transformer.optimizer import AdamW, get_lr_schedule
from jarvis_learning.transformer.reproducibility import get_deterministic_rng, reproducible_scope
from jarvis_learning.transformer.resource_estimator import ResourceEstimate, ResourceEstimator
from jarvis_learning.transformer.runtime_adapter import TransformerToolPolicyModel
from jarvis_learning.transformer.task_schema import TaskRecord
from jarvis_learning.transformer.tokenizer import ByteTokenizer, CharTokenizer
from jarvis_learning.transformer.tokenizer_metadata import TokenizerMetadata
from jarvis_learning.transformer.trainer import NanoTrainer, TrainingVerificationResult

__all__ = [
    "AbstentionConfig",
    "AbstentionDecision",
    "AbstentionTriggered",
    "AdamW",
    "AttentionExplainer",
    "BatchTensors",
    "ByteTokenizer",
    "CausalLMHead",
    "CharTokenizer",
    "CheckpointCompatibilityError",
    "CheckpointMetadata",
    "CrossEntropyLoss",
    "DatasetAdapter",
    "DimensionMismatchError",
    "GradientCheckFailedError",
    "KVCache",
    "LastValidTokenPooling",
    "LayerNorm",
    "LearnedPositionalEncoding",
    "MultiHeadAttention",
    "NanoTrainer",
    "NanoTransformer",
    "OutcomePredictionHead",
    "PositionwiseFeedForward",
    "ResourceBudgetExceededError",
    "ResourceEstimate",
    "ResourceEstimator",
    "ScaledDotProductAttention",
    "SinusoidalPositionalEncoding",
    "TaskRecord",
    "TokenAttribution",
    "TokenEmbedding",
    "TokenizerError",
    "TokenizerMetadata",
    "ToolClassificationHead",
    "TrainingVerificationResult",
    "TransformerBlock",
    "TransformerConfig",
    "TransformerError",
    "TransformerToolPolicyModel",
    "check_gradients",
    "clip_grad_norm",
    "compute_grad_norm",
    "gelu",
    "gelu_prime",
    "generate_autoregressive",
    "get_deterministic_rng",
    "get_lr_schedule",
    "load_checkpoint",
    "reproducible_scope",
    "sample_next_token",
    "save_checkpoint",
    "scale_gradients",
]
