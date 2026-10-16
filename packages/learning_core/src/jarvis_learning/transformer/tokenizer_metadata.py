"""Tokenizer metadata and provenance verification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any


@dataclass(frozen=True, slots=True)
class TokenizerMetadata:
    """Tracks tokenizer specification, vocab size, special tokens, and checksum."""

    tokenizer_type: str
    vocab_size: int
    pad_id: int
    bos_id: int
    eos_id: int
    unk_id: int
    special_tokens: dict[str, int]
    checksum: str

    @classmethod
    def create(
        cls,
        tokenizer_type: str,
        vocab_size: int,
        pad_id: int,
        bos_id: int,
        eos_id: int,
        unk_id: int,
        special_tokens: dict[str, int],
    ) -> TokenizerMetadata:
        payload = {
            "type": tokenizer_type,
            "vocab_size": vocab_size,
            "special": sorted(special_tokens.items()),
        }
        raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        checksum = hashlib.sha256(raw_bytes).hexdigest()
        return cls(
            tokenizer_type=tokenizer_type,
            vocab_size=vocab_size,
            pad_id=pad_id,
            bos_id=bos_id,
            eos_id=eos_id,
            unk_id=unk_id,
            special_tokens=dict(special_tokens),
            checksum=checksum,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenizerMetadata:
        return cls(
            tokenizer_type=str(data["tokenizer_type"]),
            vocab_size=int(data["vocab_size"]),
            pad_id=int(data["pad_id"]),
            bos_id=int(data["bos_id"]),
            eos_id=int(data["eos_id"]),
            unk_id=int(data["unk_id"]),
            special_tokens={str(k): int(v) for k, v in data.get("special_tokens", {}).items()},
            checksum=str(data["checksum"]),
        )
