"""jarvis.agents.embedded_agent_runner.tool_call_argument_decoding — HTML-entity decoding wrapper.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/tool-call-argument-decoding.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`create_html_entity_tool_call_argument_decoding_wrapper` —
  wrap a stream function so tool-call arguments are decoded
  before downstream execution.

Phase 7.4a — focused minimal port.

The OpenClaw source uses :func:`decodeHtmlEntities` from
``shared/html-entities.js`` and :func:`visitObjectContentBlocks`
from ``shared/message-content-blocks.js``. The Python port keeps
the same public surface but delegates to installable hooks so
the host can plug in the real shared formatters when they land.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Set


#: HTML-entity decoder. The host installs the real
#: :func:`decodeHtmlEntities`` when the shared html-entities
#: layer lands. The default is a no-op.
_DECODE_HTML_ENTITIES: Callable[[str], str] = lambda value: value


def set_decode_html_entities_hook(
    hook: Callable[[str], str],
) -> None:
    """Install a custom HTML-entities decoder hook."""
    global _DECODE_HTML_ENTITIES
    _DECODE_HTML_ENTITIES = hook


#: Object-content-block visitor. The host installs the real
#: :func:`visitObjectContentBlocks`` when the shared
#: message-content-blocks layer lands. The default visits
#: ``content`` lists of message-like records.
_VISIT_OBJECT_CONTENT_BLOCKS: Callable[[Any, Callable[[Any], None]], None] = (
    lambda message, visit: _default_visit_object_content_blocks(message, visit)
)


def set_visit_object_content_blocks_hook(
    hook: Callable[[Any, Callable[[Any], None]], None],
) -> None:
    """Install a custom visit-object-content-blocks hook."""
    global _VISIT_OBJECT_CONTENT_BLOCKS
    _VISIT_OBJECT_CONTENT_BLOCKS = hook


def _default_visit_object_content_blocks(
    message: Any,
    visit: Callable[[Any], None],
) -> None:
    """Default content-block visitor.

    Recursively walks an object graph, calling ``visit(block)`` for
    each item in any list it finds under the ``content`` key.
    """
    if not message or not isinstance(message, dict):
        return
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                visit(block)
    # Recurse one level into nested structures.
    for key, value in message.items():
        if key == "content":
            continue
        if isinstance(value, dict):
            _default_visit_object_content_blocks(value, visit)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _default_visit_object_content_blocks(item, visit)


def _decode_html_entities_in_object(value: Any) -> Any:
    """Recursively decode HTML entities in string leaves.

    Mirrors :func:`decodeHtmlEntitiesInObject``
    (``tool-call-argument-decoding.ts:15-31``).
    """
    if isinstance(value, str):
        return _DECODE_HTML_ENTITIES(value)
    if isinstance(value, list):
        return [_decode_html_entities_in_object(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _decode_html_entities_in_object(entry)
            for key, entry in value.items()
        }
    return value


#: Process-local set tracking already-decoded tool-call argument
#: objects so we don't decode them twice.
_DECODED_TOOL_CALL_ARGUMENTS: Set[int] = set()


def _decode_tool_call_arguments_html_entities_in_message(
    message: Any,
) -> None:
    """Decode HTML entities in tool-call arguments inside ``message``.

    Mirrors :func:`decodeToolCallArgumentsHtmlEntitiesInMessage``
    (``tool-call-argument-decoding.ts:35-52``).
    """
    if not message:
        return

    def _visit_block(block: Any) -> None:
        if not isinstance(block, dict):
            return
        if block.get("type") != "toolCall":
            return
        args = block.get("arguments")
        if not isinstance(args, dict):
            return
        args_id = id(args)
        if args_id in _DECODED_TOOL_CALL_ARGUMENTS:
            return
        decoded = _decode_html_entities_in_object(args)
        if isinstance(decoded, dict):
            _DECODED_TOOL_CALL_ARGUMENTS.add(id(decoded))
        block["arguments"] = decoded

    _VISIT_OBJECT_CONTENT_BLOCKS(message, _visit_block)


def _wrap_stream_message_objects(
    stream: Any,
    transform_message: Callable[[Any], None],
) -> Any:
    """Wrap a stream so its result + events get ``transform_message`` applied.

    Mirrors :func:`wrapStreamMessageObjects``
    (``tool-call-argument-decoding.ts:54-90``).
    """
    if stream is None:
        return stream
    original_result = getattr(stream, "result", None)
    if callable(original_result):
        async def _patched_result() -> Any:
            message = await original_result()
            transform_message(message)
            return message

        stream.result = _patched_result
    original_iter = getattr(stream, "__aiter__", None)
    if callable(original_iter):
        async def _patched_iter() -> Any:
            iterator = original_iter()
            return _PatchedAsyncIterator(iterator, transform_message)

        stream.__aiter__ = _patched_iter
    return stream


class _PatchedAsyncIterator:
    """Async-iterator wrapper that transforms message events.

    Mirrors the inline iterator patch in
    :func:`wrapStreamMessageObjects`.
    """

    def __init__(
        self,
        iterator: Any,
        transform_message: Callable[[Any], None],
    ) -> None:
        self._iterator = iterator
        self._transform_message = transform_message

    def __aiter__(self) -> "_PatchedAsyncIterator":
        return self

    async def __anext__(self) -> Any:
        result = await self._iterator.__anext__()
        if result and isinstance(result, dict):
            self._transform_message(result.get("partial"))
            self._transform_message(result.get("message"))
        return result

    async def aclose(self) -> None:
        aclose = getattr(self._iterator, "aclose", None)
        if aclose is not None:
            await aclose()


def create_html_entity_tool_call_argument_decoding_wrapper(
    base_stream_fn: Any,
) -> Any:
    """Wrap a stream function so tool-call arguments are decoded.

    Mirrors :func:`createHtmlEntityToolCallArgumentDecodingWrapper``
    (``tool-call-argument-decoding.ts:92-103``).
    """

    def _wrapper(model: Any, context: Any, options: Any) -> Any:
        maybe_stream = base_stream_fn(model, context, options)
        if maybe_stream is not None and hasattr(maybe_stream, "__await__"):
            async def _await_and_wrap() -> Any:
                stream = await maybe_stream
                return _wrap_stream_message_objects(
                    stream, _decode_tool_call_arguments_html_entities_in_message
                )

            return _await_and_wrap()
        return _wrap_stream_message_objects(
            maybe_stream,
            _decode_tool_call_arguments_html_entities_in_message,
        )

    return _wrapper


__all__ = [
    "create_html_entity_tool_call_argument_decoding_wrapper",
    "set_decode_html_entities_hook",
    "set_visit_object_content_blocks_hook",
]
