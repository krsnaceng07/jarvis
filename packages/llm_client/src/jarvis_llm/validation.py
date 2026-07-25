"""jarvis_llm.validation — tool-argument validation and coercion.

OpenClaw parity: ``packages/llm-core/src/validation.ts`` (375 LOC).
Public surface: :func:`validate_tool_call`, :func:`validate_tool_arguments`.

What this module is for
=======================
Models emit tool arguments as JSON that is *usually* right and
occasionally wrong in predictable ways: a number sent as ``"3"``, a
boolean as ``"true"``, an object as a JSON string. OpenClaw does not
reject those — it coerces them against the declared schema first and only
fails on what cannot be repaired. Reproducing the coercion rules exactly
matters, because a stricter port would reject calls OpenClaw accepts and
the agent would visibly behave worse on the same model output.

The TypeBox deviation
=====================
The TS original compiles ``tool.parameters`` with TypeBox
(``Compile`` → ``Check`` / ``Convert`` / ``Errors``). Python has no
TypeBox, and this package is deliberately dependency-free (mirroring
``plugin_sdk``), so:

- ``Convert`` — TypeBox's own conservative coercion — is **not** ported
  separately. The TS file exists precisely because ``Convert`` is too
  conservative for plain JSON schemas, and it then applies
  :func:`_coerce_with_json_schema` over the top. That second pass is the
  one that does the real work, and it is ported verbatim.
- ``Check`` and ``Errors`` are implemented here as :func:`_check` and
  :func:`_collect_errors` over the JSON Schema subset that tool
  parameters use: ``type``, ``properties``, ``required``,
  ``additionalProperties``, ``items``, ``enum``, ``const``,
  ``allOf``/``anyOf``/``oneOf``, and the numeric/length/pattern bounds.

Consequence to be aware of: an exotic schema keyword outside that subset
is *ignored* rather than enforced, so this validator is equal-or-more
permissive than TypeBox, never stricter. That direction is the safe one —
a tool receiving an argument its schema should have rejected fails in the
tool with a clear error, whereas wrongly rejecting a valid call breaks a
turn the model got right.
"""

from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass
from typing import Any

from .types import Tool, ToolCall

#: Maximum string length accepted for schema-gated JSON coercion.
#: Parity: ``MAX_JSON_COERCE_LENGTH = 64 * 1024``.
MAX_JSON_COERCE_LENGTH = 64 * 1024

#: Parity: ``JSON_NUMBER_TOKEN_RE``. Anchored, case-insensitive exponent.
_JSON_NUMBER_TOKEN_RE = re.compile(r"^[+-]?(?:(?:\d+\.?\d*)|(?:\.\d+))(?:e[+-]?\d+)?$", re.IGNORECASE)

#: Largest integer JS treats as safe; ``Number.isSafeInteger`` parity.
_MAX_SAFE_INTEGER = 2**53 - 1


class ToolValidationError(ValueError):
    """Raised when tool arguments cannot be validated against the schema.

    Parity: the plain ``Error`` thrown by ``validateToolCall`` /
    ``validateToolArguments``. A named type is used so the loop's tool
    runner can distinguish a schema rejection (which becomes a tool-result
    error the model can retry from) from an internal bug.
    """


# ── JS type predicates ───────────────────────────────────────────────
#
# These exist because Python's type model does not line up with JSON's,
# and getting the mismatches wrong is the main way a port like this
# silently diverges. The three that matter:
#   - `bool` is a subclass of `int` in Python but is *not* a JSON number.
#   - JSON has one number type; `1.0` is a valid JSON "integer".
#   - `None` is JSON `null`, not "absent".


def _is_record(value: object) -> bool:
    """JSON object test. Parity: ``isRecord``.

    TS's ``typeof value === "object" && value !== null`` is true for
    arrays too, and callers pair it with an explicit ``!Array.isArray``
    check. Python has distinct types, so this is just ``dict``.
    """
    return isinstance(value, dict)


def _is_json_number(value: object) -> bool:
    """``typeof value === "number"`` — excludes bool, excludes NaN/Inf.

    JSON has no NaN or Infinity, so a float carrying one is not a valid
    JSON number even though Python accepts it.
    """
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def _is_json_integer(value: object) -> bool:
    """``Number.isInteger`` parity — ``2.0`` counts as an integer."""
    if not _is_json_number(value):
        return False
    return float(value).is_integer()


def _matches_json_type(value: object, type_name: str) -> bool:
    """Parity: ``matchesJsonType``."""
    if type_name == "number":
        return _is_json_number(value)
    if type_name == "integer":
        return _is_json_integer(value)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "null":
        return value is None
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "object":
        return _is_record(value)
    return False


def _get_schema_types(schema: dict[str, Any]) -> list[str]:
    """Normalize ``type`` to a list. Parity: ``getSchemaTypes``."""
    declared = schema.get("type")
    if isinstance(declared, str):
        return [declared]
    if isinstance(declared, list):
        return [entry for entry in declared if isinstance(entry, str)]
    return []


# ── numeric string parsing ───────────────────────────────────────────


def _parse_json_number_string(value: str) -> float | int | None:
    """Parity: ``parseJsonNumberString``.

    The regex gate is what stops Python's much more liberal ``float()``
    from accepting things JSON never would — ``"1_0"``, ``"nan"``,
    ``"inf"``, ``"0x10"``. Dropping it would make the port accept
    arguments OpenClaw rejects.
    """
    trimmed = value.strip()
    if not trimmed or not _JSON_NUMBER_TOKEN_RE.match(trimmed):
        return None
    try:
        parsed = float(trimmed)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    # Preserve integer-ness the way JSON.parse effectively does for the
    # downstream `integer` check, without changing the numeric value.
    if parsed.is_integer() and abs(parsed) <= _MAX_SAFE_INTEGER:
        return int(parsed)
    return parsed


def _parse_json_integer_string(value: str) -> int | None:
    """Parity: ``parseJsonIntegerString`` (``Number.isSafeInteger`` gate)."""
    parsed = _parse_json_number_string(value)
    if parsed is None:
        return None
    if not float(parsed).is_integer():
        return None
    if abs(parsed) > _MAX_SAFE_INTEGER:
        return None
    return int(parsed)


# ── primitive coercion ───────────────────────────────────────────────


def _coerce_primitive_by_type(value: Any, type_name: str) -> Any:
    """Coerce one value toward one JSON type. Parity: ``coercePrimitiveByType``.

    Returns *value* unchanged when no rule applies; the caller detects
    "no change" by identity/equality and moves on to the next candidate
    type, so returning the input unchanged is meaningful, not a failure.
    """
    if type_name == "number":
        if value is None:
            return 0
        if isinstance(value, str) and value.strip():
            parsed = _parse_json_number_string(value)
            if parsed is not None:
                return parsed
        if isinstance(value, bool):
            return 1 if value else 0
        return value

    if type_name == "integer":
        if value is None:
            return 0
        if isinstance(value, str) and value.strip():
            parsed = _parse_json_integer_string(value)
            if parsed is not None:
                return parsed
        if isinstance(value, bool):
            return 1 if value else 0
        return value

    if type_name == "boolean":
        if value is None:
            return False
        if isinstance(value, str):
            if value == "true":
                return True
            if value == "false":
                return False
        # Order matters: `isinstance(True, int)` is True in Python, so the
        # bool branch above must come first or `True` would be compared
        # against 1 and returned as a "number".
        if _is_json_number(value):
            if value == 1:
                return True
            if value == 0:
                return False
        return value

    if type_name == "string":
        if value is None:
            return ""
        if isinstance(value, bool):
            # JS `String(true)` is "true", not Python's "True".
            return "true" if value else "false"
        if _is_json_number(value):
            return _js_number_to_string(value)
        return value

    if type_name == "array":
        parsed = _try_parse_json(value)
        if isinstance(parsed, list):
            return parsed
        return value

    if type_name == "object":
        parsed = _try_parse_json(value)
        if _is_record(parsed):
            return parsed
        return value

    if type_name == "null":
        # Parity: `value === "" || value === 0 || value === false`.
        # Written with explicit type checks because in Python
        # `0 == False` is True, which would conflate the branches.
        if value == "" and isinstance(value, str):
            return None
        if isinstance(value, bool):
            return None if value is False else value
        if _is_json_number(value) and value == 0:
            return None
        return value

    return value


def _try_parse_json(value: Any) -> Any:
    """Parse a bounded, non-blank string as JSON; return ``None`` on failure.

    The length bound is a denial-of-service guard: tool arguments come
    from model output, and an unbounded ``json.loads`` on a hostile
    megabyte-long string is cheap to send and expensive to parse.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    if len(value) > MAX_JSON_COERCE_LENGTH:
        return None
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        # Not valid JSON; leave as-is for the validator to reject.
        return None


def _js_number_to_string(value: float | int) -> str:
    """Render a number the way JS ``String(n)`` does.

    Needed because Python renders ``3.0`` as ``"3.0"`` while JS renders
    it as ``"3"``. A schema expecting ``"3"`` would otherwise see a value
    that looks coerced but does not match.
    """
    if isinstance(value, int):
        return str(value)
    if float(value).is_integer() and abs(value) < 1e21:
        return str(int(value))
    return repr(value)


# ── structural coercion ──────────────────────────────────────────────


def _apply_schema_object_coercion(value: dict[str, Any], schema: dict[str, Any]) -> None:
    """Coerce object members in place. Parity: ``applySchemaObjectCoercion``."""
    properties = schema.get("properties")
    defined_keys = set(properties.keys()) if _is_record(properties) else set()

    if _is_record(properties):
        for key, property_schema in properties.items():
            if key in value and _is_record(property_schema):
                value[key] = _coerce_with_json_schema(value[key], property_schema)

    additional = schema.get("additionalProperties")
    if additional and _is_record(additional):
        for key in list(value.keys()):
            if key not in defined_keys:
                value[key] = _coerce_with_json_schema(value[key], additional)


def _apply_schema_array_coercion(value: list[Any], schema: dict[str, Any]) -> None:
    """Coerce array items in place. Parity: ``applySchemaArrayCoercion``.

    Handles both tuple form (``items`` is a list, positional) and the
    single-schema form, matching the TS branch order.
    """
    items = schema.get("items")

    if isinstance(items, list):
        for index in range(len(value)):
            if index < len(items) and _is_record(items[index]):
                value[index] = _coerce_with_json_schema(value[index], items[index])
        return

    if _is_record(items):
        for index in range(len(value)):
            value[index] = _coerce_with_json_schema(value[index], items)


def _coerce_with_union_schema(value: Any, schemas: list[Any]) -> Any:
    """Coerce against ``anyOf``/``oneOf``. Parity: ``coerceWithUnionSchema``.

    The ``null`` pre-pass is load-bearing and is commented as such in the
    TS source: without it, ``anyOf [{string}, {null}]`` coerces ``null``
    to ``""`` via the string branch and never reaches the null branch.
    """
    members = [schema for schema in schemas if _is_record(schema)]

    if value is None:
        for schema in members:
            if "null" in _get_schema_types(schema) and _check(value, schema):
                return value

    for schema in members:
        candidate = copy.deepcopy(value)
        coerced = _coerce_with_json_schema(candidate, schema)
        if _check(coerced, schema):
            return coerced

    return value


def _coerce_with_json_schema(value: Any, schema: dict[str, Any]) -> Any:
    """Coerce a value toward a schema. Parity: ``coerceWithJsonSchema``.

    Order is significant and follows the TS exactly: ``allOf`` chains,
    then ``anyOf``, then ``oneOf``, then primitive type coercion, then
    recursion into object/array members.
    """
    next_value = value

    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for nested in all_of:
            if _is_record(nested):
                next_value = _coerce_with_json_schema(next_value, nested)

    any_of = schema.get("anyOf")
    if isinstance(any_of, list):
        next_value = _coerce_with_union_schema(next_value, any_of)

    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        next_value = _coerce_with_union_schema(next_value, one_of)

    schema_types = _get_schema_types(schema)
    # For a union of types, a value already matching any member is left
    # alone — coercing it would pick an arbitrary member and lose data.
    matches_union_member = len(schema_types) > 1 and any(
        _matches_json_type(next_value, schema_type) for schema_type in schema_types
    )
    if schema_types and not matches_union_member:
        for schema_type in schema_types:
            candidate = _coerce_primitive_by_type(next_value, schema_type)
            if not _same_json_value(candidate, next_value):
                next_value = candidate
                break

    if "object" in schema_types and _is_record(next_value):
        _apply_schema_object_coercion(next_value, schema)

    if "array" in schema_types and isinstance(next_value, list):
        _apply_schema_array_coercion(next_value, schema)

    return next_value


def _same_json_value(left: Any, right: Any) -> bool:
    """TS ``candidate !== nextValue`` equivalent for the coercion loop.

    Plain ``==`` is wrong here: ``0 == False`` and ``1 == True`` in
    Python, so coercing ``False`` to ``0`` would look like "no change"
    and the loop would try the next type instead of accepting the
    coercion. Type identity is compared first.
    """
    if type(left) is not type(right):
        return False
    if isinstance(left, (dict, list)):
        # Containers are coerced in place, so identity is the right test.
        return left is right
    return bool(left == right)


# ── validation (TypeBox Check / Errors replacement) ──────────────────


@dataclass(frozen=True)
class _ValidationIssue:
    """One validation failure. Stands in for ``TLocalizedValidationError``."""

    path: str
    message: str


def _check(value: Any, schema: Any) -> bool:
    """Whether *value* satisfies *schema*. Parity: ``validator.Check``."""
    return not _collect_errors(value, schema, "")


def _collect_errors(value: Any, schema: Any, path: str) -> list[_ValidationIssue]:
    """Validate and return every failure. Parity: ``validator.Errors``.

    Unknown keywords are ignored by design — see the module docstring on
    why permissive-not-strict is the safe direction for this deviation.
    """
    if not _is_record(schema):
        # A non-object schema constrains nothing (``true`` in JSON Schema).
        return []

    issues: list[_ValidationIssue] = []

    schema_types = _get_schema_types(schema)
    if schema_types and not any(
        _matches_json_type(value, schema_type) for schema_type in schema_types
    ):
        return [
            _ValidationIssue(
                path=path or "root",
                message=f"Expected {' or '.join(schema_types)}",
            )
        ]

    if "const" in schema and not _json_equal(value, schema["const"]):
        issues.append(
            _ValidationIssue(path=path or "root", message=f"Expected {schema['const']!r}")
        )

    enum = schema.get("enum")
    if isinstance(enum, list) and not any(_json_equal(value, option) for option in enum):
        allowed = ", ".join(repr(option) for option in enum)
        issues.append(
            _ValidationIssue(path=path or "root", message=f"Expected one of: {allowed}")
        )

    issues.extend(_check_combinators(value, schema, path))

    if _is_record(value):
        issues.extend(_check_object(value, schema, path))
    elif isinstance(value, list):
        issues.extend(_check_array(value, schema, path))
    elif isinstance(value, str):
        issues.extend(_check_string(value, schema, path))
    elif _is_json_number(value):
        issues.extend(_check_number(value, schema, path))

    return issues


def _check_combinators(value: Any, schema: dict[str, Any], path: str) -> list[_ValidationIssue]:
    issues: list[_ValidationIssue] = []

    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for nested in all_of:
            issues.extend(_collect_errors(value, nested, path))

    any_of = schema.get("anyOf")
    if isinstance(any_of, list) and any_of:
        if not any(_check(value, nested) for nested in any_of):
            issues.append(
                _ValidationIssue(
                    path=path or "root", message="Value does not match any allowed schema"
                )
            )

    one_of = schema.get("oneOf")
    if isinstance(one_of, list) and one_of:
        matched = sum(1 for nested in one_of if _check(value, nested))
        if matched != 1:
            issues.append(
                _ValidationIssue(
                    path=path or "root",
                    message=f"Expected exactly one matching schema, matched {matched}",
                )
            )

    not_schema = schema.get("not")
    if _is_record(not_schema) and _check(value, not_schema):
        issues.append(
            _ValidationIssue(path=path or "root", message="Value matches a forbidden schema")
        )

    return issues


def _check_object(
    value: dict[str, Any], schema: dict[str, Any], path: str
) -> list[_ValidationIssue]:
    issues: list[_ValidationIssue] = []
    properties = schema.get("properties")
    property_schemas = properties if _is_record(properties) else {}

    required = schema.get("required")
    if isinstance(required, list):
        for key in required:
            if isinstance(key, str) and key not in value:
                issues.append(
                    _ValidationIssue(
                        path=_join_path(path, key), message="Required property missing"
                    )
                )

    for key, member in value.items():
        if key in property_schemas:
            issues.extend(_collect_errors(member, property_schemas[key], _join_path(path, key)))
            continue
        additional = schema.get("additionalProperties")
        if additional is False:
            issues.append(
                _ValidationIssue(
                    path=_join_path(path, key), message="Additional property not allowed"
                )
            )
        elif _is_record(additional):
            issues.extend(_collect_errors(member, additional, _join_path(path, key)))

    return issues


def _check_array(value: list[Any], schema: dict[str, Any], path: str) -> list[_ValidationIssue]:
    issues: list[_ValidationIssue] = []
    items = schema.get("items")

    if isinstance(items, list):
        for index, member in enumerate(value):
            if index < len(items):
                issues.extend(_collect_errors(member, items[index], _join_path(path, str(index))))
    elif _is_record(items):
        for index, member in enumerate(value):
            issues.extend(_collect_errors(member, items, _join_path(path, str(index))))

    min_items = schema.get("minItems")
    if isinstance(min_items, int) and not isinstance(min_items, bool) and len(value) < min_items:
        issues.append(
            _ValidationIssue(path=path or "root", message=f"Expected at least {min_items} items")
        )

    max_items = schema.get("maxItems")
    if isinstance(max_items, int) and not isinstance(max_items, bool) and len(value) > max_items:
        issues.append(
            _ValidationIssue(path=path or "root", message=f"Expected at most {max_items} items")
        )

    return issues


def _check_string(value: str, schema: dict[str, Any], path: str) -> list[_ValidationIssue]:
    issues: list[_ValidationIssue] = []

    min_length = schema.get("minLength")
    if isinstance(min_length, int) and not isinstance(min_length, bool) and len(value) < min_length:
        issues.append(
            _ValidationIssue(
                path=path or "root", message=f"Expected string length >= {min_length}"
            )
        )

    max_length = schema.get("maxLength")
    if isinstance(max_length, int) and not isinstance(max_length, bool) and len(value) > max_length:
        issues.append(
            _ValidationIssue(
                path=path or "root", message=f"Expected string length <= {max_length}"
            )
        )

    pattern = schema.get("pattern")
    if isinstance(pattern, str):
        try:
            compiled = re.compile(pattern)
        except re.error:
            # An un-compilable pattern is the schema author's bug, not the
            # model's; enforcing nothing beats rejecting a valid call.
            return issues
        if compiled.search(value) is None:
            issues.append(
                _ValidationIssue(path=path or "root", message=f"Expected match for /{pattern}/")
            )

    return issues


def _check_number(value: Any, schema: dict[str, Any], path: str) -> list[_ValidationIssue]:
    issues: list[_ValidationIssue] = []

    minimum = schema.get("minimum")
    if _is_json_number(minimum) and value < minimum:
        issues.append(_ValidationIssue(path=path or "root", message=f"Expected >= {minimum}"))

    maximum = schema.get("maximum")
    if _is_json_number(maximum) and value > maximum:
        issues.append(_ValidationIssue(path=path or "root", message=f"Expected <= {maximum}"))

    exclusive_minimum = schema.get("exclusiveMinimum")
    if _is_json_number(exclusive_minimum) and value <= exclusive_minimum:
        issues.append(
            _ValidationIssue(path=path or "root", message=f"Expected > {exclusive_minimum}")
        )

    exclusive_maximum = schema.get("exclusiveMaximum")
    if _is_json_number(exclusive_maximum) and value >= exclusive_maximum:
        issues.append(
            _ValidationIssue(path=path or "root", message=f"Expected < {exclusive_maximum}")
        )

    multiple_of = schema.get("multipleOf")
    if _is_json_number(multiple_of) and multiple_of != 0:
        remainder = math.fmod(float(value), float(multiple_of))
        if not math.isclose(remainder, 0.0, abs_tol=1e-9) and not math.isclose(
            abs(remainder), abs(float(multiple_of)), abs_tol=1e-9
        ):
            issues.append(
                _ValidationIssue(
                    path=path or "root", message=f"Expected multiple of {multiple_of}"
                )
            )

    return issues


def _json_equal(left: Any, right: Any) -> bool:
    """Structural JSON equality that does not conflate ``0``/``False``."""
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_equal(a, b) for a, b in zip(left, right)
        )
    return bool(left == right)


def _join_path(path: str, key: str) -> str:
    """Build the dotted path used in error messages.

    Parity: ``formatValidationPath`` produces dotted paths from TypeBox's
    ``instancePath``, with required-property failures reported at the
    missing child rather than the parent. Constructing the path as we
    descend gets the same strings without an ``instancePath`` to rewrite.
    """
    return f"{path}.{key}" if path else key


# ── public surface ───────────────────────────────────────────────────


def validate_tool_call(tools: list[Tool], tool_call: ToolCall) -> Any:
    """Find the target tool and validate/coerce a model-emitted call.

    Parity: ``validateToolCall``. Raises :class:`ToolValidationError` when
    the named tool is not registered — matching ``Tool "x" not found``.
    """
    for candidate in tools:
        if candidate.name == tool_call.name:
            return validate_tool_arguments(candidate, tool_call)
    raise ToolValidationError(f'Tool "{tool_call.name}" not found')


def validate_tool_arguments(tool: Tool, tool_call: ToolCall) -> Any:
    """Validate and coerce arguments against the tool's parameter schema.

    Parity: ``validateToolArguments``. Returns the coerced arguments;
    raises :class:`ToolValidationError` with the multi-line message shape
    the TS builds, including the received arguments as pretty JSON, since
    that text is fed back to the model as a tool-result error and its
    shape is what the model has learned to repair from.

    The input is deep-copied first (TS: ``structuredClone``) so a rejected
    call leaves ``tool_call.arguments`` untouched for the error message.
    """
    args = copy.deepcopy(tool_call.arguments)
    schema = tool.parameters

    if _is_record(schema):
        coerced = _coerce_with_json_schema(args, schema)
        if not _same_json_value(coerced, args):
            if _is_record(args) and _is_record(coerced):
                args.clear()
                args.update(coerced)
            else:
                return coerced if _check(coerced, schema) else args
        else:
            args = coerced

    if _check(args, schema):
        return args

    issues = _collect_errors(args, schema, "")
    detail = (
        "\n".join(f"  - {issue.path}: {issue.message}" for issue in issues)
        or "Unknown validation error"
    )
    received = json.dumps(tool_call.arguments, indent=2, default=str)
    raise ToolValidationError(
        f'Validation failed for tool "{tool_call.name}":\n{detail}\n\n'
        f"Received arguments:\n{received}"
    )


__all__ = [
    "MAX_JSON_COERCE_LENGTH",
    "ToolValidationError",
    "validate_tool_arguments",
    "validate_tool_call",
]
