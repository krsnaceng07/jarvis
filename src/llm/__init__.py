"""jarvis.llm — LLM facade.

OpenClaw parity: mirrors ``src/llm/`` (the thin facade over
the providers — providers themselves live in extensions).

Re-export shim: a follow-up phase will physically move
``jarvis_sdk.{expect_runtime,lazy_runtime,number_runtime,runtime_env}``
here and update all import sites.
"""
from __future__ import annotations

from jarvis_sdk.expect_runtime import expect_value  # noqa: F401
from jarvis_sdk.lazy_runtime import Lazy  # noqa: F401
from jarvis_sdk.number_runtime import parse_float, parse_int  # noqa: F401
from jarvis_sdk.runtime_env import get_env, require_env  # noqa: F401
from jarvis_sdk.memory_embeddings import embed_query, embed_text  # noqa: F401
