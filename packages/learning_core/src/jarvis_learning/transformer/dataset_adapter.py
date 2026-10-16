"""Adapters converting Wave 2 DatasetSamples and TaskRecords into tokenized Transformer tensors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
import numpy as np

from jarvis_learning.transformer.task_schema import TaskRecord
from jarvis_learning.transformer.tokenizer import BaseTokenizer


@dataclass(frozen=True, slots=True)
class BatchTensors:
    """Standardized batch tensor container for Transformer forward/backward."""

    input_ids: np.ndarray  # (B, T) int64
    padding_mask: np.ndarray  # (B, T) bool (True=valid, False=pad)
    labels: np.ndarray  # (B,) int64 for classification, or (B, T) for LM


class DatasetAdapter:
    """Transforms raw task records into padded, aligned Transformer tensors."""

    def __init__(self, tokenizer: BaseTokenizer, max_seq_len: int = 128) -> None:
        self.tokenizer = tokenizer
        self.max_seq_len = max_seq_len

    def tokenize_records(
        self,
        records: Sequence[TaskRecord],
        label_mapping: dict[str, int] | None = None,
    ) -> BatchTensors:
        """Tokenizes and aligns records into fixed-width padded batch tensors."""
        b = len(records)
        if b == 0:
            return BatchTensors(
                input_ids=np.empty((0, self.max_seq_len), dtype=np.int64),
                padding_mask=np.empty((0, self.max_seq_len), dtype=bool),
                labels=np.empty((0,), dtype=np.int64),
            )

        pad_id = self.tokenizer.metadata.pad_id
        input_ids = np.full((b, self.max_seq_len), pad_id, dtype=np.int64)
        padding_mask = np.zeros((b, self.max_seq_len), dtype=bool)
        labels_list: list[int] = []

        for i, rec in enumerate(records):
            tokens = self.tokenizer.encode(rec.input_text, add_bos=True, add_eos=False)
            if len(tokens) > self.max_seq_len:
                tokens = tokens[: self.max_seq_len]

            seq_len = len(tokens)
            input_ids[i, :seq_len] = tokens
            padding_mask[i, :seq_len] = True

            # Resolve target label
            target = rec.target_label
            if label_mapping is not None and isinstance(target, str):
                target_idx = label_mapping.get(target, 0)
            elif isinstance(target, (int, np.integer)):
                target_idx = int(target)
            else:
                target_idx = 0
            labels_list.append(target_idx)

        labels = np.array(labels_list, dtype=np.int64)
        return BatchTensors(input_ids=input_ids, padding_mask=padding_mask, labels=labels)

    @staticmethod
    def grouped_split(
        records: Sequence[TaskRecord], val_ratio: float = 0.2, seed: int = 42
    ) -> tuple[list[TaskRecord], list[TaskRecord]]:
        """Splits records into train and validation sets grouped strictly by session_id."""
        sessions: dict[str, list[TaskRecord]] = {}
        for r in records:
            s_id = r.session_id if r.session_id else f"default_{r.task_id}"
            sessions.setdefault(s_id, []).append(r)

        session_keys = sorted(sessions.keys())
        rng = np.random.default_rng(seed)
        rng.shuffle(session_keys)

        num_val = max(1, int(len(session_keys) * val_ratio))
        val_sessions = set(session_keys[:num_val])

        train_records: list[TaskRecord] = []
        val_records: list[TaskRecord] = []

        for s_id, s_records in sessions.items():
            if s_id in val_sessions:
                val_records.extend(s_records)
            else:
                train_records.extend(s_records)

        return train_records, val_records
