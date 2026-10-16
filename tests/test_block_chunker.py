"""Tests for src/agents/block_chunker.py.

Mirrors embedded-agent-block-chunker tests in OpenClaw.
"""

from __future__ import annotations


from src.agents.block_chunker import (
    BlockReplyChunking,
    EmbeddedBlockChunker,
    HumanDelayPacer,
    parse_fence_spans,
)


def test_parse_fence_spans():
    text = "Hello\n```python\nprint('hi')\n```\nWorld"
    spans = parse_fence_spans(text)
    assert len(spans) == 1
    assert spans[0].start == text.find("```python")
    assert spans[0].end == text.find("```\n") + 3


def test_block_chunker_min_chars():
    chunker = EmbeddedBlockChunker(BlockReplyChunking(min_chars=20, max_chars=100))
    chunker.append("Short")
    chunks = []
    chunker.drain(force=False, emit=chunks.append)
    assert len(chunks) == 0  # Under min_chars, not forced

    chunker.drain(force=True, emit=chunks.append)
    assert chunks == ["Short"]


def test_block_chunker_paragraph_break():
    chunker = EmbeddedBlockChunker(BlockReplyChunking(min_chars=10, max_chars=50, break_preference="paragraph"))
    chunker.append("First paragraph text.\n\nSecond paragraph text is long enough.")
    chunks = []
    chunker.drain(force=False, emit=chunks.append)
    assert len(chunks) >= 1
    assert chunks[0] == "First paragraph text.\n\n"


def test_human_delay_pacer():
    pacer_off = HumanDelayPacer(mode="off")
    assert pacer_off.get_delay_seconds() == 0.0

    pacer_nat = HumanDelayPacer(mode="natural")
    delay = pacer_nat.get_delay_seconds()
    assert 0.8 <= delay <= 2.5

    pacer_cust = HumanDelayPacer(mode="custom", min_ms=100, max_ms=200)
    delay_c = pacer_cust.get_delay_seconds()
    assert 0.1 <= delay_c <= 0.2
