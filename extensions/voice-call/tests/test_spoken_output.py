"""Unit tests for defensive spoken output contract formatting and parsing."""

from __future__ import annotations

from extensions.voice_call.src.spoken_output import (
    append_spoken_output_contract,
    extract_spoken_output_text,
)


def test_append_spoken_output_contract() -> None:
    # Empty prompt
    contract_only = append_spoken_output_contract(None)
    assert "[SPOKEN OUTPUT CONTRACT]" in contract_only
    assert '{"spoken": "Your spoken reply text here"}' in contract_only

    # Existing prompt
    existing = "You are a customer support agent."
    appended = append_spoken_output_contract(existing)
    assert appended.startswith("You are a customer support agent.")
    assert "[SPOKEN OUTPUT CONTRACT]" in appended


def test_extract_spoken_output_defensive() -> None:
    # 1. Direct dict
    assert extract_spoken_output_text({"spoken": "Hello from dict"}) == "Hello from dict"
    assert extract_spoken_output_text({"text": "Hello text"}) == "Hello text"

    # 2. Direct JSON string
    assert extract_spoken_output_text('{"spoken": "Hello direct JSON"}') == "Hello direct JSON"

    # 3. Fenced code block
    fenced = '```json\n{\n  "spoken": "Hello from code block"\n}\n```'
    assert extract_spoken_output_text(fenced) == "Hello from code block"

    # 4. Inline JSON match
    inline = 'Here is the response: {"spoken": "Hello inline text"}'
    assert extract_spoken_output_text(inline) == "Hello inline text"

    # 5. Thought tags stripped and plain text fallback
    with_thought = (
        "<thought>Thinking about what to say to the user.</thought>\n\n"
        "Hello! I am ready to help you with your question."
    )
    assert (
        extract_spoken_output_text(with_thought)
        == "Hello! I am ready to help you with your question."
    )

    # 6. Planning lead-in stripped
    with_planning = (
        "Thinking Process:\n1. User asked for status\n2. Status is green\n\n"
        "Your system status is completely green and operational."
    )
    assert (
        extract_spoken_output_text(with_planning)
        == "Your system status is completely green and operational."
    )
