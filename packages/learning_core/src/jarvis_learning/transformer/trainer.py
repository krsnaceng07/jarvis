"""NanoTrainer for training Transformer trunk and heads with empirical loss verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import numpy as np

from jarvis_learning.transformer.dataset_adapter import BatchTensors
from jarvis_learning.transformer.gradients import clip_grad_norm
from jarvis_learning.transformer.heads import LastValidTokenPooling, ToolClassificationHead
from jarvis_learning.transformer.loss import CrossEntropyLoss
from jarvis_learning.transformer.model import NanoTransformer
from jarvis_learning.transformer.optimizer import AdamW, get_lr_schedule


@dataclass
class TrainingVerificationResult:
    """Empirical training verification result (replaces false step monotonicity)."""

    initial_loss: float
    final_loss: float
    loss_reduced: bool
    parameters_updated: bool
    no_nans_or_infs: bool
    training_accuracy: float
    is_verified: bool
    step_losses: list[float] = field(default_factory=list)


class NanoTrainer:
    """Trains NanoTransformer + Task Head end-to-end with AdamW and analytical backprop."""

    def __init__(
        self,
        model: NanoTransformer,
        head: ToolClassificationHead,
        lr: float = 1e-3,
        weight_decay: float = 0.01,
        max_grad_norm: float = 1.0,
        warmup_steps: int = 10,
        max_steps: int = 100,
    ) -> None:
        self.model = model
        self.head = head
        self.pooling = LastValidTokenPooling()
        self.loss_fn = CrossEntropyLoss()

        self.lr = lr
        self.max_grad_norm = max_grad_norm
        self.warmup_steps = warmup_steps
        self.max_steps = max_steps

        # Bundle model and head parameters for AdamW
        self.params: dict[str, Any] = {
            "token_embedding": self.model.token_embedding.weight,
            "final_ln": {
                "gamma": self.model.final_ln.gamma,
                "beta": self.model.final_ln.beta,
            },
            "head": {
                "w": self.head.w,
                "b": self.head.b,
            },
            "blocks": [],
        }

        for b in self.model.blocks:
            b_dict = {
                "ln1": {"gamma": b.ln1.gamma, "beta": b.ln1.beta},
                "mha": {
                    "wq": b.mha.wq,
                    "wk": b.mha.wk,
                    "wv": b.mha.wv,
                    "wo": b.mha.wo,
                },
                "ln2": {"gamma": b.ln2.gamma, "beta": b.ln2.beta},
                "ffn": {
                    "w1": b.ffn.w1,
                    "w2": b.ffn.w2,
                },
            }
            if b.mha.bq is not None:
                b_dict["mha"]["bq"] = b.mha.bq
                b_dict["mha"]["bk"] = b.mha.bk
                b_dict["mha"]["bv"] = b.mha.bv
                b_dict["mha"]["bo"] = b.mha.bo
            if b.ffn.b1 is not None:
                b_dict["ffn"]["b1"] = b.ffn.b1
                b_dict["ffn"]["b2"] = b.ffn.b2
            self.params["blocks"].append(b_dict)

        if self.model.config.positional_encoding == "learned":
            self.params["pos_encoding"] = self.model.pos_encoding.weight

        self.optimizer = AdamW(self.params, lr=lr, weight_decay=weight_decay)
        self.step_losses: list[float] = []

    def train_step(self, batch: BatchTensors, step: int) -> tuple[float, float]:
        """Executes one forward pass, loss calculation, backward pass, and optimizer step."""
        # 1. Forward pass
        hidden, _ = self.model.forward(
            batch.input_ids, padding_mask=batch.padding_mask, causal=True
        )
        pooled = self.pooling.forward(hidden, padding_mask=batch.padding_mask)
        logits = self.head.forward(pooled)

        # 2. Loss & Accuracy
        loss = self.loss_fn.forward(logits, batch.labels)
        preds = np.argmax(logits, axis=-1)
        accuracy = float(np.mean(preds == batch.labels))

        # 3. Backward pass
        grad_logits = self.loss_fn.backward()
        grad_pooled, head_grads = self.head.backward(grad_logits)
        grad_hidden = self.pooling.backward(grad_pooled)
        trunk_grads = self.model.backward(grad_hidden)

        # Assemble full grad structure matching self.params
        grads: dict[str, Any] = {
            "token_embedding": trunk_grads["token_embedding"]["weight"],
            "final_ln": trunk_grads["final_ln"],
            "head": head_grads,
            "blocks": trunk_grads["blocks"],
        }
        if "pos_encoding" in trunk_grads:
            grads["pos_encoding"] = trunk_grads["pos_encoding"]["weight"]

        # 4. Clip gradients
        clipped_grads, _ = clip_grad_norm(grads, self.max_grad_norm)

        # 5. Optimizer step with LR schedule
        current_lr = get_lr_schedule(
            step=step,
            base_lr=self.lr,
            warmup_steps=self.warmup_steps,
            max_steps=self.max_steps,
        )
        self.optimizer.step(clipped_grads, current_lr=current_lr)
        self.step_losses.append(loss)

        return loss, accuracy

    def train(self, batch: BatchTensors, epochs: int = 50) -> TrainingVerificationResult:
        """Trains for specified epochs and performs empirical verification."""
        initial_loss: float = 0.0
        final_loss: float = 0.0
        final_acc: float = 0.0

        # Snapshot initial head weights to verify parameters update
        init_head_w = self.head.w.copy()

        for ep in range(epochs):
            loss, acc = self.train_step(batch, step=ep)
            if ep == 0:
                initial_loss = loss
            final_loss = loss
            final_acc = acc

        # Check empirical verification criteria
        loss_reduced = final_loss < initial_loss
        no_nans = not any(np.isnan(loss_val) or np.isinf(loss_val) for loss_val in self.step_losses)
        param_delta = float(np.linalg.norm(self.head.w - init_head_w))
        params_updated = param_delta > 1e-4

        is_verified = loss_reduced and no_nans and params_updated

        return TrainingVerificationResult(
            initial_loss=initial_loss,
            final_loss=final_loss,
            loss_reduced=loss_reduced,
            parameters_updated=params_updated,
            no_nans_or_infs=no_nans,
            training_accuracy=final_acc,
            is_verified=is_verified,
            step_losses=list(self.step_losses),
        )
