"""Tests for src/plugins/llama_cpp.py.

Mirrors tests of extensions/llama-cpp/src/defaults.ts in OpenClaw.
"""

from __future__ import annotations


from src.plugins.llama_cpp import (
    DEFAULT_LLAMA_CPP_CONTEXT_SIZE,
    DEFAULT_LLAMA_CPP_EMBEDDING_MODEL_URI,
    DEFAULT_LLAMA_CPP_MODEL_ID,
    DEFAULT_LLAMA_CPP_MODEL_URI,
    LLAMA_CPP_PROVIDER_ID,
    meets_llama_cpp_ram_floor,
    resolve_llama_cpp_model_cache_dir,
    resolve_llama_cpp_model_config,
)


def test_llama_cpp_constants():
    assert LLAMA_CPP_PROVIDER_ID == "llama-cpp"
    assert DEFAULT_LLAMA_CPP_MODEL_ID == "gemma-4-e4b-it-q4_k_m"
    assert DEFAULT_LLAMA_CPP_MODEL_URI == "hf:unsloth/gemma-4-E4B-it-GGUF/gemma-4-E4B-it-Q4_K_M.gguf"
    assert (
        DEFAULT_LLAMA_CPP_EMBEDDING_MODEL_URI
        == "hf:ggml-org/embeddinggemma-300m-qat-q8_0-GGUF/embeddinggemma-300m-qat-Q8_0.gguf"
    )
    assert DEFAULT_LLAMA_CPP_CONTEXT_SIZE == 8192


def test_meets_llama_cpp_ram_floor():
    assert meets_llama_cpp_ram_floor(16 * 1024 * 1024 * 1024) is True
    assert meets_llama_cpp_ram_floor(32 * 1024 * 1024 * 1024) is True
    assert meets_llama_cpp_ram_floor(8 * 1024 * 1024 * 1024) is False


def test_resolve_llama_cpp_model_cache_dir():
    d = resolve_llama_cpp_model_cache_dir()
    assert d.endswith(".jarvis\\models\\llama.cpp") or d.endswith(".jarvis/models/llama.cpp")

    custom = resolve_llama_cpp_model_cache_dir("~/Models/custom")
    assert custom.endswith("Models/custom") or custom.endswith("Models\\custom")


def test_resolve_llama_cpp_model_config_defaults():
    cfg = resolve_llama_cpp_model_config(None)
    assert cfg.id == DEFAULT_LLAMA_CPP_MODEL_ID
    assert cfg.model_path == DEFAULT_LLAMA_CPP_MODEL_URI
    assert cfg.context_size == 8192
    assert cfg.supports_tools is True


def test_resolve_llama_cpp_model_config_custom():
    model_cfg = {
        "id": "my-local-model",
        "params": {
            "modelPath": "~/Models/my-model.Q4_K_M.gguf",
            "contextSize": 16384,
        },
        "compat": {"supportsTools": False},
    }
    cfg = resolve_llama_cpp_model_config(model_cfg)
    assert cfg.id == "my-local-model"
    assert cfg.model_path == "~/Models/my-model.Q4_K_M.gguf"
    assert cfg.context_size == 16384
    assert cfg.supports_tools is False
