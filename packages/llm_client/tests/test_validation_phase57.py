"""Phase 5.7: tool-argument validation and coercion parity.

Ports the behavioural expectations of
``openclaw-main/packages/llm-core/src/validation.ts`` into tests. Each case
here corresponds to a coercion rule in that file; the point is that JARVIS
accepts exactly the model output OpenClaw accepts, since a stricter port
would reject valid tool calls and make the agent visibly worse on
identical model output.

Also covered: the Python-specific traps that a naive port falls into —
``bool`` being a subclass of ``int``, ``0 == False``, ``str(3.0)`` giving
``"3.0"`` where JS gives ``"3"``, and ``float()`` accepting tokens JSON
never would.
"""

from __future__ import annotations

from typing import Any

import pytest

from jarvis_llm.types import Tool, ToolCall
from jarvis_llm.validation import (
    ToolValidationError,
    validate_tool_arguments,
    validate_tool_call,
)


def _tool(parameters: dict[str, Any]) -> Tool:
    return Tool(name="t", description="d", parameters=parameters)


def _call(arguments: dict[str, Any]) -> ToolCall:
    return ToolCall(id="1", name="t", arguments=arguments)


def _obj(**properties: Any) -> dict[str, Any]:
    return {"type": "object", "properties": dict(properties)}


# ── primitive coercion (coercePrimitiveByType parity) ────────────────


@pytest.mark.parametrize(
    ("schema_type", "given", "expected"),
    [
        ("number", "3", 3),
        ("number", "3.5", 3.5),
        ("number", "-2e3", -2000),
        ("number", None, 0),
        ("number", True, 1),
        ("number", False, 0),
        ("integer", "42", 42),
        ("integer", None, 0),
        ("boolean", "true", True),
        ("boolean", "false", False),
        ("boolean", 1, True),
        ("boolean", 0, False),
        ("boolean", None, False),
        ("string", None, ""),
        ("string", 7, "7"),
        ("string", True, "true"),
        ("string", False, "false"),
    ],
)
def test_primitive_coercion(schema_type: str, given: Any, expected: Any) -> None:
    tool = _tool(_obj(v={"type": schema_type}))
    result = validate_tool_arguments(tool, _call({"v": given}))
    assert result == {"v": expected}
    # Guard against 0/False and 1/True conflation, which `==` alone misses.
    assert type(result["v"]) is type(expected)


def test_string_from_float_uses_js_formatting() -> None:
    """JS ``String(3.0)`` is ``"3"``; Python's ``str`` would give ``"3.0"``."""
    tool = _tool(_obj(s={"type": "string"}))
    assert validate_tool_arguments(tool, _call({"s": 3.0})) == {"s": "3"}


@pytest.mark.parametrize("given", ["1_0", "nan", "inf", "0x10", "", "  ", "1,000"])
def test_non_json_number_tokens_rejected(given: str) -> None:
    """The regex gate stops Python's liberal ``float()`` from over-accepting."""
    tool = _tool(_obj(n={"type": "number"}))
    with pytest.raises(ToolValidationError):
        validate_tool_arguments(tool, _call({"n": given}))


def test_unsafe_integer_string_not_coerced() -> None:
    """``Number.isSafeInteger`` parity — beyond 2**53-1 the value is not trusted."""
    tool = _tool(_obj(n={"type": "integer"}))
    with pytest.raises(ToolValidationError):
        validate_tool_arguments(tool, _call({"n": "9007199254740993"}))


# ── JSON-string coercion for containers ──────────────────────────────


def test_json_string_object_coerced() -> None:
    tool = _tool(_obj(o={"type": "object", "properties": {"k": {"type": "string"}}}))
    assert validate_tool_arguments(tool, _call({"o": '{"k":"v"}'})) == {"o": {"k": "v"}}


def test_json_string_array_coerced() -> None:
    tool = _tool(_obj(xs={"type": "array", "items": {"type": "integer"}}))
    assert validate_tool_arguments(tool, _call({"xs": "[1, 2, 3]"})) == {"xs": [1, 2, 3]}


def test_json_string_of_wrong_shape_not_coerced() -> None:
    """An array literal must not satisfy ``type: object``."""
    tool = _tool(_obj(o={"type": "object"}))
    with pytest.raises(ToolValidationError):
        validate_tool_arguments(tool, _call({"o": "[1,2]"}))


def test_oversized_json_string_not_parsed() -> None:
    """DoS guard: tool arguments are model output, so the parse is bounded."""
    tool = _tool(_obj(o={"type": "object"}))
    payload = '{"k":"' + "x" * 70_000 + '"}'
    with pytest.raises(ToolValidationError):
        validate_tool_arguments(tool, _call({"o": payload}))


# ── unions ───────────────────────────────────────────────────────────


def test_nullable_union_keeps_null() -> None:
    """The load-bearing null pre-pass, commented as such in the TS source.

    Without it, ``anyOf [{string}, {null}]`` coerces ``None`` to ``""``
    through the string branch and never reaches the null branch.
    """
    tool = _tool(_obj(s={"anyOf": [{"type": "string"}, {"type": "null"}]}))
    assert validate_tool_arguments(tool, _call({"s": None})) == {"s": None}


def test_nullable_union_still_coerces_non_null() -> None:
    tool = _tool(_obj(n={"anyOf": [{"type": "number"}, {"type": "null"}]}))
    assert validate_tool_arguments(tool, _call({"n": "5"})) == {"n": 5}


def test_union_leaves_already_matching_value_alone() -> None:
    """A value matching any member must not be coerced toward another."""
    tool = _tool(_obj(v={"type": ["string", "number"]}))
    result = validate_tool_arguments(tool, _call({"v": "text"}))
    assert result == {"v": "text"}


def test_one_of_requires_exactly_one_match() -> None:
    tool = _tool(_obj(v={"oneOf": [{"type": "string"}, {"type": "number"}]}))
    assert validate_tool_arguments(tool, _call({"v": "x"})) == {"v": "x"}


# ── nesting ──────────────────────────────────────────────────────────


def test_nested_object_properties_coerced() -> None:
    tool = _tool(_obj(outer=_obj(inner={"type": "integer"})))
    assert validate_tool_arguments(tool, _call({"outer": {"inner": "9"}})) == {
        "outer": {"inner": 9}
    }


def test_array_items_coerced() -> None:
    tool = _tool(_obj(xs={"type": "array", "items": {"type": "integer"}}))
    assert validate_tool_arguments(tool, _call({"xs": ["1", "2"]})) == {"xs": [1, 2]}


def test_tuple_form_items_coerced_positionally() -> None:
    tool = _tool(_obj(pair={"type": "array", "items": [{"type": "integer"}, {"type": "string"}]}))
    assert validate_tool_arguments(tool, _call({"pair": ["1", 2]})) == {"pair": [1, "2"]}


def test_additional_properties_schema_coerced() -> None:
    tool = _tool(
        {
            "type": "object",
            "properties": {"known": {"type": "string"}},
            "additionalProperties": {"type": "integer"},
        }
    )
    assert validate_tool_arguments(tool, _call({"known": "a", "extra": "3"})) == {
        "known": "a",
        "extra": 3,
    }


# ── rejection ────────────────────────────────────────────────────────


def test_required_missing_rejected_with_child_path() -> None:
    """Parity: required failures are reported at the missing child, not the parent."""
    tool = _tool({**_obj(n={"type": "number"}), "required": ["n"]})
    with pytest.raises(ToolValidationError) as excinfo:
        validate_tool_arguments(tool, _call({}))
    message = str(excinfo.value)
    assert "n: Required property missing" in message
    assert "Received arguments:" in message


def test_uncoercible_value_rejected() -> None:
    tool = _tool(_obj(n={"type": "number"}))
    with pytest.raises(ToolValidationError):
        validate_tool_arguments(tool, _call({"n": "not a number"}))


def test_enum_enforced() -> None:
    tool = _tool(_obj(m={"enum": ["a", "b"]}))
    assert validate_tool_arguments(tool, _call({"m": "a"})) == {"m": "a"}
    with pytest.raises(ToolValidationError):
        validate_tool_arguments(tool, _call({"m": "c"}))


def test_additional_properties_false_rejected() -> None:
    tool = _tool({**_obj(a={"type": "string"}), "additionalProperties": False})
    with pytest.raises(ToolValidationError):
        validate_tool_arguments(tool, _call({"a": "x", "b": "y"}))


def test_numeric_bounds_enforced() -> None:
    tool = _tool(_obj(n={"type": "integer", "minimum": 1, "maximum": 10}))
    assert validate_tool_arguments(tool, _call({"n": "5"})) == {"n": 5}
    with pytest.raises(ToolValidationError):
        validate_tool_arguments(tool, _call({"n": "11"}))


def test_string_pattern_enforced() -> None:
    tool = _tool(_obj(s={"type": "string", "pattern": "^[a-z]+$"}))
    assert validate_tool_arguments(tool, _call({"s": "abc"})) == {"s": "abc"}
    with pytest.raises(ToolValidationError):
        validate_tool_arguments(tool, _call({"s": "ABC"}))


def test_uncompilable_pattern_enforces_nothing() -> None:
    """A broken schema is the author's bug; rejecting a valid call is worse."""
    tool = _tool(_obj(s={"type": "string", "pattern": "([unclosed"}))
    assert validate_tool_arguments(tool, _call({"s": "anything"})) == {"s": "anything"}


def test_unknown_tool_rejected() -> None:
    with pytest.raises(ToolValidationError) as excinfo:
        validate_tool_call([], _call({}))
    assert 'Tool "t" not found' in str(excinfo.value)


def test_validate_tool_call_dispatches_by_name() -> None:
    wanted = Tool(name="wanted", description="d", parameters=_obj(n={"type": "integer"}))
    other = Tool(name="other", description="d", parameters={})
    call = ToolCall(id="1", name="wanted", arguments={"n": "4"})
    assert validate_tool_call([other, wanted], call) == {"n": 4}


# ── the input must not be mutated on rejection ───────────────────────


def test_original_arguments_untouched_on_failure() -> None:
    """The error message quotes the *received* arguments, so they must survive."""
    tool = _tool({**_obj(n={"type": "number"}), "required": ["n"]})
    original = {"n": "bad", "nested": {"k": "v"}}
    call = _call(original)
    with pytest.raises(ToolValidationError):
        validate_tool_arguments(tool, call)
    assert call.arguments == {"n": "bad", "nested": {"k": "v"}}


def test_original_arguments_untouched_on_success() -> None:
    tool = _tool(_obj(n={"type": "integer"}))
    call = _call({"n": "7"})
    assert validate_tool_arguments(tool, call) == {"n": 7}
    assert call.arguments == {"n": "7"}, "coercion must work on a copy"


def test_empty_schema_accepts_anything() -> None:
    """A tool declaring no parameters must not reject arguments."""
    tool = _tool({})
    assert validate_tool_arguments(tool, _call({"anything": [1, "two"]})) == {
        "anything": [1, "two"]
    }
