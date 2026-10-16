from src.sessions.model_registry import (
    register_model,
    resolve_model,
    list_models,
)


def test_register_and_resolve_by_name():
    register_model(id="m1", name="gpt-test", provider="openai", params={"max_tokens": 1024})
    mr = resolve_model("gpt-test")
    assert mr is not None
    assert mr.id == "m1"
    assert mr.provider == "openai"


def test_register_and_resolve_by_id():
    register_model(id="m2", name="claude-haiku", provider="anthropic", params={"context_window": 8192}, auth_profile="default")
    mr = resolve_model("m2")
    assert mr is not None
    assert mr.name == "claude-haiku"
    assert mr.auth_profile == "default"


def test_list_models_contains_registered():
    before = {m.id for m in list_models()}
    register_model(id="m3", name="test-3", provider="gemini")
    ids = {m.id for m in list_models()}
    assert "m3" in ids
    assert ids.issuperset(before)
