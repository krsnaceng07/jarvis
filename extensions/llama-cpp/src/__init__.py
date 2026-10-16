"""llama.cpp provider extension package."""

from .backends import detect_execution_backend
from .config import LlamaCppConfig, resolve_llama_cpp_config
from .doctor import run_llama_cpp_doctor
from .models import (
    DEFAULT_EMBEDDING_MODEL,
    RECOMMENDED_MODELS,
    HardwareMetrics,
    LlamaCppModelSpec,
    get_all_models_catalog,
    recommend_model_for_hardware,
)
from .probe import probe_llama_server
from .setup import get_llama_cpp_setup_status
from .verifier import verify_managed_model_candidate

__all__ = [
    "detect_execution_backend",
    "LlamaCppConfig",
    "resolve_llama_cpp_config",
    "run_llama_cpp_doctor",
    "DEFAULT_EMBEDDING_MODEL",
    "RECOMMENDED_MODELS",
    "HardwareMetrics",
    "LlamaCppModelSpec",
    "get_all_models_catalog",
    "recommend_model_for_hardware",
    "probe_llama_server",
    "get_llama_cpp_setup_status",
    "verify_managed_model_candidate",
]
