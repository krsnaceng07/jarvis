"""Byte and Char tokenizers with guaranteed lossless byte roundtripping."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Sequence
import numpy as np

from jarvis_learning.transformer.tokenizer_metadata import TokenizerMetadata

PAD_ID = 0
BOS_ID = 1
EOS_ID = 2
UNK_ID = 3
BYTE_OFFSET = 4
BYTE_VOCAB_SIZE = 260


class BaseTokenizer(ABC):
    """Abstract base class for tokenizers."""

    @abstractmethod
    def encode(self, text: str, add_bos: bool = False, add_eos: bool = False) -> np.ndarray:
        """Encodes text to a 1D numpy array of token IDs (dtype=int64)."""

    @abstractmethod
    def decode(self, ids: Sequence[int] | np.ndarray, strip_special: bool = True) -> str:
        """Decodes token IDs to string."""

    @property
    @abstractmethod
    def vocab_size(self) -> int:
        """Total vocabulary size."""

    @property
    @abstractmethod
    def metadata(self) -> TokenizerMetadata:
        """Tokenizer metadata with checksum."""


class ByteTokenizer(BaseTokenizer):
    """Zero-OOD byte tokenizer mapping arbitrary bytes to IDs 4..259.

    Special tokens:
    0: PAD
    1: BOS
    2: EOS
    3: UNK
    4..259: Raw byte values 0x00..0xFF

    Guarantees:
    decode_bytes(encode_bytes(b)) == b for ANY byte sequence b.
    """

    def __init__(self) -> None:
        self._special_tokens = {
            "<pad>": PAD_ID,
            "<bos>": BOS_ID,
            "<eos>": EOS_ID,
            "<unk>": UNK_ID,
        }
        self._meta = TokenizerMetadata.create(
            tokenizer_type="byte",
            vocab_size=BYTE_VOCAB_SIZE,
            pad_id=PAD_ID,
            bos_id=BOS_ID,
            eos_id=EOS_ID,
            unk_id=UNK_ID,
            special_tokens=self._special_tokens,
        )

    @property
    def vocab_size(self) -> int:
        return BYTE_VOCAB_SIZE

    @property
    def pad_id(self) -> int:
        return PAD_ID

    @property
    def bos_id(self) -> int:
        return BOS_ID

    @property
    def eos_id(self) -> int:
        return EOS_ID

    @property
    def unk_id(self) -> int:
        return UNK_ID

    @property
    def metadata(self) -> TokenizerMetadata:
        return self._meta

    def encode_bytes(self, data: bytes, add_bos: bool = False, add_eos: bool = False) -> np.ndarray:
        """Encodes raw bytes to an array of token IDs."""
        byte_arr = np.frombuffer(data, dtype=np.uint8).astype(np.int64) + BYTE_OFFSET
        parts = []
        if add_bos:
            parts.append(np.array([BOS_ID], dtype=np.int64))
        if len(byte_arr) > 0:
            parts.append(byte_arr)
        if add_eos:
            parts.append(np.array([EOS_ID], dtype=np.int64))

        if not parts:
            return np.empty((0,), dtype=np.int64)
        return np.concatenate(parts, axis=0)

    def decode_bytes(self, ids: Sequence[int] | np.ndarray, strip_special: bool = True) -> bytes:
        """Decodes token IDs directly into raw bytes."""
        arr = np.asarray(ids, dtype=np.int64)
        if arr.ndim != 1:
            arr = arr.flatten()

        out = bytearray()
        for token_id in arr:
            if token_id < BYTE_OFFSET:
                if not strip_special:
                    pass
            elif token_id < BYTE_VOCAB_SIZE:
                out.append(int(token_id - BYTE_OFFSET))
            else:
                pass
        return bytes(out)

    def encode(self, text: str, add_bos: bool = False, add_eos: bool = False) -> np.ndarray:
        """Encodes UTF-8 string to byte token IDs."""
        data = text.encode("utf-8")
        return self.encode_bytes(data, add_bos=add_bos, add_eos=add_eos)

    def decode(
        self, ids: Sequence[int] | np.ndarray, strip_special: bool = True, errors: str = "replace"
    ) -> str:
        """Decodes token IDs to UTF-8 string with explicit error handling."""
        raw_bytes = self.decode_bytes(ids, strip_special=strip_special)
        return raw_bytes.decode("utf-8", errors=errors)


class CharTokenizer(BaseTokenizer):
    """Character-level tokenizer with custom vocabulary support."""

    def __init__(self, vocab_chars: str | None = None) -> None:
        if vocab_chars is None:
            chars = [chr(i) for i in range(32, 127)] + ["\n", "\t", "\r"]
        else:
            chars = sorted(set(vocab_chars))

        self._special_tokens = {
            "<pad>": PAD_ID,
            "<bos>": BOS_ID,
            "<eos>": EOS_ID,
            "<unk>": UNK_ID,
        }
        self._char_to_id: dict[str, int] = dict(self._special_tokens)
        self._id_to_char: dict[int, str] = {v: k for k, v in self._special_tokens.items()}

        curr_id = 4
        for ch in chars:
            if ch not in self._char_to_id:
                self._char_to_id[ch] = curr_id
                self._id_to_char[curr_id] = ch
                curr_id += 1

        self._vocab_size = curr_id
        self._meta = TokenizerMetadata.create(
            tokenizer_type="char",
            vocab_size=self._vocab_size,
            pad_id=PAD_ID,
            bos_id=BOS_ID,
            eos_id=EOS_ID,
            unk_id=UNK_ID,
            special_tokens=self._special_tokens,
        )

    @property
    def vocab_size(self) -> int:
        return self._vocab_size

    @property
    def pad_id(self) -> int:
        return PAD_ID

    @property
    def bos_id(self) -> int:
        return BOS_ID

    @property
    def eos_id(self) -> int:
        return EOS_ID

    @property
    def unk_id(self) -> int:
        return UNK_ID

    @property
    def metadata(self) -> TokenizerMetadata:
        return self._meta

    def encode(self, text: str, add_bos: bool = False, add_eos: bool = False) -> np.ndarray:
        token_ids: list[int] = []
        if add_bos:
            token_ids.append(BOS_ID)
        for ch in text:
            token_ids.append(self._char_to_id.get(ch, UNK_ID))
        if add_eos:
            token_ids.append(EOS_ID)
        return np.array(token_ids, dtype=np.int64)

    def decode(self, ids: Sequence[int] | np.ndarray, strip_special: bool = True) -> str:
        arr = np.asarray(ids, dtype=np.int64)
        if arr.ndim != 1:
            arr = arr.flatten()
        chars: list[str] = []
        for tid in arr:
            if strip_special and tid in (PAD_ID, BOS_ID, EOS_ID, UNK_ID):
                continue
            chars.append(self._id_to_char.get(int(tid), ""))
        return "".join(chars)
