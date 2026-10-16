"""jarvis_learning.models.baseline — baseline models for comparison.

Implements Baseline 1 (Frequency Heuristic) and Baseline 2 (TF-IDF + Softmax
Logistic Regression in pure-Python) to enforce the baseline-first requirement:
no neural model is promoted unless it demonstrably outperforms these baselines.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from .base import LocalModel, ToolPrediction


@dataclass
class BaselineEvaluation:
    """Evaluation metrics for a baseline model."""

    accuracy: float
    brier_score: float
    total_samples: int
    correct_samples: int


class FrequencyBaseline:
    """Baseline 1: Predicts tool based on intent frequency and exact match."""

    def __init__(self) -> None:
        self._exact_map: dict[str, str] = {}
        self._class_counts: Counter[str] = Counter()
        self._most_common: str = ""

    def fit(self, samples: list[dict[str, Any]]) -> None:
        """Fit on training samples containing 'input' and 'label'."""
        self._exact_map.clear()
        self._class_counts.clear()

        for s in samples:
            inp = s.get("input_data", {})
            user_text = inp.get("user_input", "").strip().lower()
            lbl = s.get("label", {})
            tool = lbl.get("tool", "")
            if not tool:
                continue

            self._class_counts[tool] += 1
            if user_text:
                self._exact_map[user_text] = tool

        if self._class_counts:
            self._most_common = self._class_counts.most_common(1)[0][0]

    def predict(self, user_input: str) -> tuple[str, float]:
        """Predict tool name and confidence."""
        normalized = user_input.strip().lower()
        if normalized in self._exact_map:
            return self._exact_map[normalized], 0.95

        # Return most common class with its frequency as confidence
        total = sum(self._class_counts.values()) or 1
        conf = (self._class_counts[self._most_common] / total) if self._most_common else 0.1
        return self._most_common, round(conf, 4)


class TFIDFLogisticBaseline:
    """Baseline 2: Pure-Python TF-IDF feature extractor + Softmax Logistic Regression."""

    def __init__(self, ngram_range: tuple[int, int] = (1, 2), max_features: int = 2000) -> None:
        self.ngram_range = ngram_range
        self.max_features = max_features
        self.vocabulary: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        self.classes: list[str] = []
        self.class_to_idx: dict[str, int] = {}
        self.weights: list[list[float]] = []  # shape: (num_classes, num_features)
        self.biases: list[float] = []

    def _extract_ngrams(self, text: str) -> list[str]:
        words = re.findall(r"\b\w+\b", text.lower())
        tokens: list[str] = []
        for n in range(self.ngram_range[0], self.ngram_range[1] + 1):
            for i in range(len(words) - n + 1):
                tokens.append(" ".join(words[i : i + n]))
        return tokens

    def fit(
        self,
        samples: list[dict[str, Any]],
        *,
        epochs: int = 25,
        lr: float = 0.1,
        l2_reg: float = 0.001,
    ) -> None:
        """Train pure-python TF-IDF vectorizer + Softmax SGD model."""
        if not samples:
            return

        # 1. Build vocabulary & IDF
        doc_count = len(samples)
        df_counts: Counter[str] = Counter()
        all_doc_tokens: list[list[str]] = []
        all_labels: list[str] = []

        for s in samples:
            text = s.get("input_data", {}).get("user_input", "")
            tool = s.get("label", {}).get("tool", "")
            tokens = self._extract_ngrams(text)
            all_doc_tokens.append(tokens)
            all_labels.append(tool)
            for token in set(tokens):
                df_counts[token] += 1

        # Select top features
        most_common_terms = [t for t, _ in df_counts.most_common(self.max_features)]
        self.vocabulary = {term: idx for idx, term in enumerate(most_common_terms)}
        num_features = len(self.vocabulary)

        # Compute smoothed IDF: log((N + 1) / (DF + 1)) + 1
        self.idf = {
            term: math.log((doc_count + 1) / (df_counts[term] + 1)) + 1.0
            for term in self.vocabulary
        }

        # 2. Build classes
        self.classes = sorted(list(set(lbl for lbl in all_labels if lbl)))
        self.class_to_idx = {c: idx for idx, c in enumerate(self.classes)}
        num_classes = len(self.classes)

        if num_classes < 2 or num_features == 0:
            return

        # 3. Vectorize dataset
        X: list[list[float]] = []
        y: list[int] = []
        for tokens, label in zip(all_doc_tokens, all_labels):
            if label not in self.class_to_idx:
                continue
            vec = self._vectorize_tokens(tokens)
            X.append(vec)
            y.append(self.class_to_idx[label])

        # 4. Initialize weights and biases
        self.weights = [[0.0] * num_features for _ in range(num_classes)]
        self.biases = [0.0] * num_classes

        # 5. Mini-batch / SGD optimization
        for _ in range(epochs):
            for i in range(len(X)):
                xi = X[i]
                target_cls = y[i]

                # Compute class logits: W * x + b
                logits = [
                    sum(w_c * x_k for w_c, x_k in zip(self.weights[c], xi)) + self.biases[c]
                    for c in range(num_classes)
                ]

                # Softmax with max-logit stabilization
                max_l = max(logits)
                exps = [math.exp(lg - max_l) for lg in logits]
                sum_exps = sum(exps)
                probs = [e / sum_exps for e in exps]

                # Gradients: (prob_c - 1{c == target})
                for c in range(num_classes):
                    error = probs[c] - (1.0 if c == target_cls else 0.0)
                    for k in range(num_features):
                        if xi[k] != 0.0:
                            grad = error * xi[k] + l2_reg * self.weights[c][k]
                            self.weights[c][k] -= lr * grad
                    self.biases[c] -= lr * error

    def _vectorize_tokens(self, tokens: list[str]) -> list[float]:
        num_features = len(self.vocabulary)
        vec = [0.0] * num_features
        token_counts = Counter(tokens)
        for t, count in token_counts.items():
            if t in self.vocabulary:
                idx = self.vocabulary[t]
                tf = count / len(tokens) if tokens else 0.0
                vec[idx] = tf * self.idf[t]
        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def predict(self, user_input: str) -> tuple[str, float]:
        """Return (predicted_tool, probability)."""
        if not self.classes or not self.weights:
            return "", 0.0

        tokens = self._extract_ngrams(user_input)
        vec = self._vectorize_tokens(tokens)
        num_classes = len(self.classes)

        logits = [
            sum(w_c * x_k for w_c, x_k in zip(self.weights[c], vec)) + self.biases[c]
            for c in range(num_classes)
        ]
        max_l = max(logits)
        exps = [math.exp(lg - max_l) for lg in logits]
        sum_exps = sum(exps) or 1.0
        probs = [e / sum_exps for e in exps]

        best_idx = int(max(range(num_classes), key=lambda c: probs[c]))
        return self.classes[best_idx], round(probs[best_idx], 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ngram_range": list(self.ngram_range),
            "max_features": self.max_features,
            "vocabulary": self.vocabulary,
            "idf": self.idf,
            "classes": self.classes,
            "weights": self.weights,
            "biases": self.biases,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TFIDFLogisticBaseline:
        model = cls(
            ngram_range=tuple(d.get("ngram_range", [1, 2])),  # type: ignore[arg-type]
            max_features=int(d.get("max_features", 2000)),
        )
        model.vocabulary = d.get("vocabulary", {})
        model.idf = d.get("idf", {})
        model.classes = d.get("classes", [])
        model.class_to_idx = {c: idx for idx, c in enumerate(model.classes)}
        model.weights = d.get("weights", [])
        model.biases = d.get("biases", [])
        return model


class TfidfBaselineModel(LocalModel):
    """LocalModel adapter for TFIDFLogisticBaseline."""

    def __init__(
        self,
        model_id: str = "tfidf_baseline_v1",
        version: str = "v1.0.0",
        baseline: TFIDFLogisticBaseline | None = None,
    ) -> None:
        super().__init__(target="tool_policy", model_id=model_id, version=version)
        self.baseline = baseline or TFIDFLogisticBaseline()
        self._is_loaded = bool(self.baseline.classes and self.baseline.weights)

    def load(self, artifact_dir: Path) -> None:
        artifact_dir = Path(artifact_dir)
        weights_file = artifact_dir / "tfidf_weights.json"
        if not weights_file.exists():
            raise FileNotFoundError(f"TF-IDF weights file not found: {weights_file}")
        with open(weights_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.baseline = TFIDFLogisticBaseline.from_dict(data)
        self._is_loaded = True

    def save(self, artifact_dir: Path) -> None:
        artifact_dir = Path(artifact_dir)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        weights_file = artifact_dir / "tfidf_weights.json"
        with open(weights_file, "w", encoding="utf-8") as f:
            json.dump(self.baseline.to_dict(), f, indent=2)

    def predict(self, input_data: dict[str, Any]) -> ToolPrediction:
        user_input = str(input_data.get("user_input", ""))
        tool_name, prob = self.baseline.predict(user_input)
        is_finite = math.isfinite(prob)
        return ToolPrediction(
            tool_name=tool_name,
            raw_confidence=prob if is_finite else 0.0,
            calibrated_confidence=prob if is_finite else 0.0,
            confidence=prob if is_finite else 0.0,
            intent="",
            model_id=self.model_id,
            model_version=self.version,
            task_family="tool_policy",
            is_finite=is_finite,
            risk_level=(
                "low"
                if tool_name
                in {
                    "system.get_time",
                    "volume.set",
                    "volume.mute",
                    "browser.navigate_tab",
                    "app.focus",
                }
                else "medium"
            ),
            argument_strategy="deterministic",
        )

    def unload(self) -> None:
        self.baseline = TFIDFLogisticBaseline()
        self._is_loaded = False
