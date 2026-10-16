"""Tests for Wave 20 — Remaining (Secrets, i18n, Auto-reply, Context Engine)."""

from __future__ import annotations

from pathlib import Path

from src.secrets.store import SecretsStore
from src.secrets.env_resolver import resolve_secret_ref
import sys

i18n_src = Path(__file__).parent.parent / "packages" / "i18n_core" / "src"
if str(i18n_src) not in sys.path:
    sys.path.insert(0, str(i18n_src))

from jarvis_i18n import t, resolve_locale
from src.auto_reply.thinking import resolve_thinking_level
from src.context_engine.resolver import ContextEngineResolver


def test_secrets_store_and_env_resolver(tmp_path: Path):
    sec_file = tmp_path / "secrets.json"
    store = SecretsStore(secrets_file=sec_file)

    store.set_secret("OPENAI_API_KEY", "sk-12345")
    assert store.get_secret("OPENAI_API_KEY") == "sk-12345"
    assert store.list_keys() == ["OPENAI_API_KEY"]

    resolved = resolve_secret_ref("$JARVIS_SECRET:OPENAI_API_KEY", store=store)
    assert resolved == "sk-12345"

    assert store.delete_secret("OPENAI_API_KEY")
    assert store.get_secret("OPENAI_API_KEY") is None


def test_i18n():
    assert t("welcome", "en-US") == "Welcome to JARVIS"
    assert t("welcome", "np") == "JARVIS मा स्वागत छ"
    assert resolve_locale({"locale": "np"}) == "np"


def test_thinking_config():
    cfg = resolve_thinking_level("models/gemini-3.1-flash", {"thinking": {"level": "high", "budget_tokens": 4096}})
    assert cfg.level == "high"
    assert cfg.budget_tokens == 4096


def test_context_engine_resolver(tmp_path: Path):
    f = tmp_path / "sample.txt"
    f.write_text("Hello from sample file", encoding="utf-8")

    resolver = ContextEngineResolver()
    res = resolver.resolve_mentions(f"Check this out: @file:{f}")
    assert "Attached file" in res
    assert "Hello from sample file" in res
