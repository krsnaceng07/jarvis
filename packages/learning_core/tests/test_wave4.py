"""Comprehensive test suite for Wave 4 — Research Transformer Laboratory & Runtime Integration."""

from __future__ import annotations

import tempfile
from pathlib import Path
import numpy as np
import pytest

from jarvis_learning.transformer.abstention import AbstentionConfig
from jarvis_learning.transformer.attention import MultiHeadAttention
from jarvis_learning.transformer.block import TransformerBlock
from jarvis_learning.transformer.cache import KVCache
from jarvis_learning.transformer.checkpoint import (
    CheckpointCompatibilityError,
    load_checkpoint,
    save_checkpoint,
)
from jarvis_learning.transformer.config import TransformerConfig
from jarvis_learning.transformer.dataset_adapter import DatasetAdapter
from jarvis_learning.transformer.errors import (
    DimensionMismatchError,
    ResourceBudgetExceededError,
)
from jarvis_learning.transformer.explainability import AttentionExplainer
from jarvis_learning.transformer.generation import sample_next_token
from jarvis_learning.transformer.gradient_check import check_gradients
from jarvis_learning.transformer.gradients import clip_grad_norm, compute_grad_norm
from jarvis_learning.transformer.heads import (
    LastValidTokenPooling,
    ToolClassificationHead,
)
from jarvis_learning.transformer.layers import PositionwiseFeedForward
from jarvis_learning.transformer.loss import CrossEntropyLoss
from jarvis_learning.transformer.model import NanoTransformer
from jarvis_learning.transformer.normalization import LayerNorm
from jarvis_learning.transformer.optimizer import AdamW, get_lr_schedule
from jarvis_learning.transformer.resource_estimator import ResourceEstimator
from jarvis_learning.transformer.runtime_adapter import TransformerToolPolicyModel
from jarvis_learning.transformer.task_schema import TaskRecord
from jarvis_learning.transformer.tokenizer import ByteTokenizer, CharTokenizer
from jarvis_learning.transformer.trainer import NanoTrainer


# -----------------------------------------------------------------------------
# 1. Tokenizer Tests
# -----------------------------------------------------------------------------


def test_byte_tokenizer_lossless_binary_roundtrip():
    tok = ByteTokenizer()
    # Arbitrary byte sequences including null, extreme bytes, unicode artifacts
    test_cases = [
        b"",
        b"\x00",
        b"\x00\x01\x02\x03\x04\xff",
        bytes(range(256)),
        b"Hello, JARVIS Wave 4!\n\t\x00\xff",
    ]
    for raw in test_cases:
        encoded = tok.encode_bytes(raw)
        decoded = tok.decode_bytes(encoded, strip_special=True)
        assert decoded == raw, f"Failed roundtrip for {raw!r}: got {decoded!r}"


def test_byte_tokenizer_text_roundtrip():
    tok = ByteTokenizer()
    text = "Deploying NanoTransformer on CPU! \U0001f916\U0001f525"
    encoded = tok.encode(text)
    decoded = tok.decode(encoded)
    assert decoded == text


def test_char_tokenizer_roundtrip():
    tok = CharTokenizer()
    text = "print('Hello world!')\n"
    encoded = tok.encode(text)
    decoded = tok.decode(encoded)
    assert decoded == text


def test_tokenizer_metadata_checksum():
    tok = ByteTokenizer()
    meta = tok.metadata
    assert meta.tokenizer_type == "byte"
    assert meta.vocab_size == 260
    assert len(meta.checksum) == 64  # SHA-256 hex


# -----------------------------------------------------------------------------
# 2. Config & Error Tests
# -----------------------------------------------------------------------------


def test_config_valid_and_serialization():
    cfg = TransformerConfig(d_model=64, n_heads=4, d_ff=256)
    assert cfg.d_head == 16
    d = cfg.to_dict()
    restored = TransformerConfig.from_dict(d)
    assert restored == cfg


def test_config_dimension_mismatch_validation():
    with pytest.raises(DimensionMismatchError):
        TransformerConfig(d_model=65, n_heads=4)  # 65 not divisible by 4

    with pytest.raises(DimensionMismatchError):
        TransformerConfig(vocab_size=0)

    with pytest.raises(DimensionMismatchError):
        TransformerConfig(n_layers=-1)


# -----------------------------------------------------------------------------
# 3. LayerNorm & FFN Tests
# -----------------------------------------------------------------------------


def test_layernorm_forward_and_numerical_gradient():
    ln = LayerNorm(d_model=8)
    x = np.random.randn(2, 3, 8).astype(np.float64)
    y = ln.forward(x)
    assert y.shape == (2, 3, 8)

    v = np.random.randn(*y.shape).astype(np.float64)
    grad_x, param_grads = ln.backward(v)

    def func(test_x):
        return float(np.sum(ln.forward(test_x) * v))

    passed, max_err = check_gradients(func, x, grad_x, eps=1e-5, tol=1e-4)
    assert passed, f"LayerNorm gradient check failed with err {max_err}"


def test_ffn_forward_and_numerical_gradient():
    ffn = PositionwiseFeedForward(d_model=8, d_ff=16, activation="gelu")
    x = np.random.randn(2, 3, 8).astype(np.float64)
    out = ffn.forward(x)
    assert out.shape == (2, 3, 8)

    v = np.random.randn(*out.shape).astype(np.float64)
    grad_x, param_grads = ffn.backward(v)

    def func(test_x):
        return float(np.sum(ffn.forward(test_x) * v))

    passed, max_err = check_gradients(func, x, grad_x, eps=1e-5, tol=1e-4)
    assert passed, f"FFN gradient check failed with err {max_err}"


# -----------------------------------------------------------------------------
# 4. Attention & Block Tests
# -----------------------------------------------------------------------------


def test_mha_forward_and_numerical_gradient():
    mha = MultiHeadAttention(d_model=8, n_heads=2)
    x = np.random.randn(2, 3, 8).astype(np.float64)
    out, attn = mha.forward(x)
    assert out.shape == (2, 3, 8)
    assert attn.shape == (2, 2, 3, 3)

    v = np.random.randn(*out.shape).astype(np.float64)
    grad_x, param_grads = mha.backward(v)

    def func(test_x):
        o, _ = mha.forward(test_x)
        return float(np.sum(o * v))

    passed, max_err = check_gradients(func, x, grad_x, eps=1e-5, tol=1e-4)
    assert passed, f"MHA gradient check failed with err {max_err}"


def test_transformer_block_forward_backward():
    cfg = TransformerConfig(d_model=16, n_heads=2, d_ff=32, n_layers=1)
    block = TransformerBlock(cfg, layer_idx=0)
    x = np.random.randn(2, 4, 16).astype(np.float64)
    out, attn = block.forward(x)
    assert out.shape == (2, 4, 16)

    grad_x, p_grads = block.backward(np.ones_like(out))
    assert grad_x.shape == x.shape
    assert "mha" in p_grads
    assert "ffn" in p_grads


# -----------------------------------------------------------------------------
# 5. KV-Cache Equivalence Test
# -----------------------------------------------------------------------------


def test_kv_cache_equivalence():
    cfg = TransformerConfig(
        vocab_size=50, max_seq_len=32, d_model=16, n_heads=2, d_ff=32, n_layers=2
    )
    model = NanoTransformer(cfg)

    prompt = [3, 7, 11]
    cache = KVCache(cfg.n_layers)

    # Step 1: Pre-fill
    h_prompt, _ = model.forward(np.array([prompt], dtype=np.int64), causal=True, kv_cache=cache)

    # Step 2: Step 1 token
    tok1 = 19
    h_tok1, _ = model.forward(np.array([[tok1]], dtype=np.int64), causal=True, kv_cache=cache)

    # Step 3: Step 2nd token
    tok2 = 23
    h_tok2, _ = model.forward(np.array([[tok2]], dtype=np.int64), causal=True, kv_cache=cache)

    # Step 4: Full run without cache
    full_seq = prompt + [tok1, tok2]
    h_full, _ = model.forward(np.array([full_seq], dtype=np.int64), causal=True, kv_cache=None)

    diff = float(np.max(np.abs(h_tok2[0, -1, :] - h_full[0, -1, :])))
    assert diff < 1e-5, f"KV cache discrepancy {diff} exceeds tolerance"


# -----------------------------------------------------------------------------
# 6. Loss & Gradient Check Tests
# -----------------------------------------------------------------------------


def test_cross_entropy_loss_numerical_check():
    ce = CrossEntropyLoss()
    logits = np.array([[2.1, -1.2, 0.5], [-0.1, 1.8, 0.9]], dtype=np.float64)
    targets = np.array([0, 1], dtype=np.int64)

    _ = ce.forward(logits, targets)
    grad_ana = ce.backward()

    def func(test_logits):
        return ce.forward(test_logits, targets)

    passed, max_err = check_gradients(func, logits, grad_ana, eps=1e-5, tol=1e-4)
    assert passed, f"CE loss gradient check failed with err {max_err}"


def test_clip_grad_norm():
    grads = {
        "w1": np.array([3.0, 4.0]),  # norm = 5.0
        "b1": np.array([0.0]),
    }
    clipped, total_norm = clip_grad_norm(grads, max_norm=2.5)
    assert np.isclose(total_norm, 5.0)
    new_norm = compute_grad_norm(clipped)
    assert np.isclose(new_norm, 2.5, atol=1e-5)


# -----------------------------------------------------------------------------
# 7. Optimizer Tests
# -----------------------------------------------------------------------------


def test_adamw_step_and_lr_schedule():
    w = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
    b = np.array([0.0, 0.0], dtype=np.float64)
    params = {"w": w, "b": b}
    opt = AdamW(params, lr=0.1, weight_decay=0.01)

    grads = {"w": np.ones_like(w), "b": np.ones_like(b)}
    opt.step(grads)

    assert not np.allclose(w, np.array([[1.0, 2.0], [3.0, 4.0]]))
    assert not np.allclose(b, np.array([0.0, 0.0]))

    # Test lr schedule
    lr_0 = get_lr_schedule(step=0, base_lr=0.01, warmup_steps=10, max_steps=100)
    lr_5 = get_lr_schedule(step=5, base_lr=0.01, warmup_steps=10, max_steps=100)
    assert lr_5 > lr_0


# -----------------------------------------------------------------------------
# 8. Generation & Sampling Tests
# -----------------------------------------------------------------------------


def test_sample_next_token():
    logits = np.array([0.1, 5.0, 0.2], dtype=np.float64)
    # Greedy
    idx = sample_next_token(logits, temperature=0.0)
    assert idx == 1

    # Repetition penalty
    idx_pen = sample_next_token(
        logits, temperature=0.0, repetition_penalty=100.0, generated_tokens=[1]
    )
    assert idx_pen != 1  # 1 was heavily penalized


# -----------------------------------------------------------------------------
# 9. Resource Estimator & Budget Tests
# -----------------------------------------------------------------------------


def test_resource_estimator():
    cfg = TransformerConfig(
        vocab_size=260, max_seq_len=64, d_model=32, n_heads=2, d_ff=64, n_layers=2
    )
    est = ResourceEstimator.estimate(cfg)
    assert est.total_parameters > 0
    assert est.total_training_memory_bytes > 0

    # Budget validation should succeed
    ResourceEstimator.validate_budget(cfg, max_parameters=100_000, max_ram_bytes=50_000_000)

    # Budget validation should fail when limit is too low
    with pytest.raises(ResourceBudgetExceededError):
        ResourceEstimator.validate_budget(cfg, max_parameters=100)


# -----------------------------------------------------------------------------
# 10. Checkpointing Tests
# -----------------------------------------------------------------------------


def test_checkpoint_save_load_and_corruption():
    cfg = TransformerConfig(
        vocab_size=260, max_seq_len=64, d_model=32, n_heads=2, d_ff=64, n_layers=2
    )
    weights = {"w": np.ones((4, 4)), "b": np.zeros((4,))}

    with tempfile.TemporaryDirectory() as tmpdir:
        save_checkpoint(
            tmpdir,
            model_task="tool_policy",
            config=cfg,
            weights_dict=weights,
            tokenizer_checksum="tok_checksum_123",
        )
        loaded_w, loaded_m = load_checkpoint(
            tmpdir, expected_task="tool_policy", expected_tokenizer_checksum="tok_checksum_123"
        )
        assert np.allclose(loaded_w["w"], weights["w"])

        # Test corrupt SHA-256 detection
        weights_file = Path(tmpdir) / "weights.npz"
        weights_file.write_bytes(b"corrupted bytes")
        with pytest.raises(CheckpointCompatibilityError):
            load_checkpoint(tmpdir)


# -----------------------------------------------------------------------------
# 11. Dataset Adapter & Grouped Splitting Tests
# -----------------------------------------------------------------------------


def test_dataset_adapter_and_grouped_split():
    tok = ByteTokenizer()
    adapter = DatasetAdapter(tok, max_seq_len=16)

    records = [
        TaskRecord(
            task_id="1",
            task_type="tool_policy",
            input_text="open browser",
            target_label="nav",
            session_id="s1",
        ),
        TaskRecord(
            task_id="2",
            task_type="tool_policy",
            input_text="close tab",
            target_label="close",
            session_id="s1",
        ),
        TaskRecord(
            task_id="3",
            task_type="tool_policy",
            input_text="set volume",
            target_label="vol",
            session_id="s2",
        ),
        TaskRecord(
            task_id="4",
            task_type="tool_policy",
            input_text="mute",
            target_label="mute",
            session_id="s3",
        ),
    ]

    label_map = {"nav": 0, "close": 1, "vol": 2, "mute": 3}
    batch = adapter.tokenize_records(records, label_mapping=label_map)
    assert batch.input_ids.shape == (4, 16)
    assert batch.padding_mask.shape == (4, 16)
    assert len(batch.labels) == 4

    train_r, val_r = DatasetAdapter.grouped_split(records, val_ratio=0.33)
    train_sessions = {r.session_id for r in train_r}
    val_sessions = {r.session_id for r in val_r}
    # No session leakage
    assert train_sessions.isdisjoint(val_sessions)


# -----------------------------------------------------------------------------
# 12. Task Heads & LastValidTokenPooling Tests
# -----------------------------------------------------------------------------


def test_last_valid_token_pooling_and_backward():
    pooling = LastValidTokenPooling()

    hidden = np.ones((2, 3, 4), dtype=np.float64)
    # Batch item 0 has length 2; Batch item 1 has length 1
    mask = np.array([[True, True, False], [True, False, False]])
    pooled = pooling.forward(hidden, padding_mask=mask)
    assert pooled.shape == (2, 4)

    grad_pooled = np.ones_like(pooled)
    grad_h = pooling.backward(grad_pooled)
    # Verify gradient was scattered to index 1 for batch 0, and index 0 for batch 1
    assert np.all(grad_h[0, 1, :] == 1.0)
    assert np.all(grad_h[0, 2, :] == 0.0)
    assert np.all(grad_h[1, 0, :] == 1.0)
    assert np.all(grad_h[1, 1, :] == 0.0)


# -----------------------------------------------------------------------------
# 13. Trainer & Empirical Loss Verification Tests
# -----------------------------------------------------------------------------


def test_trainer_empirical_loss_verification():
    tok = ByteTokenizer()
    adapter = DatasetAdapter(tok, max_seq_len=16)

    records = [
        TaskRecord(
            task_id="1",
            task_type="tool_policy",
            input_text="open tab",
            target_label="tab",
            session_id="s1",
        ),
        TaskRecord(
            task_id="2",
            task_type="tool_policy",
            input_text="mute volume",
            target_label="mute",
            session_id="s2",
        ),
    ]
    label_map = {"tab": 0, "mute": 1}
    batch = adapter.tokenize_records(records, label_mapping=label_map)

    cfg = TransformerConfig(
        vocab_size=260, max_seq_len=16, d_model=16, n_heads=2, d_ff=32, n_layers=1
    )
    model = NanoTransformer(cfg)
    head = ToolClassificationHead(d_model=16, num_classes=2)
    trainer = NanoTrainer(model, head, lr=0.02, max_steps=30)

    result = trainer.train(batch, epochs=25)
    assert result.is_verified
    assert result.final_loss < result.initial_loss
    assert result.parameters_updated
    assert result.no_nans_or_infs
    assert result.training_accuracy == 1.0


# -----------------------------------------------------------------------------
# 14. Runtime Adapter & Crash Fallback Tests
# -----------------------------------------------------------------------------


def test_runtime_adapter_prediction_and_fallback():
    cfg = TransformerConfig(
        vocab_size=260, max_seq_len=16, d_model=16, n_heads=2, d_ff=32, n_layers=1
    )
    classes = ["browser.new_tab", "volume.mute"]
    runtime_model = TransformerToolPolicyModel(
        config=cfg, abstention_config=AbstentionConfig(min_calibrated_confidence=0.1)
    )
    runtime_model.init_model(classes)

    pred = runtime_model.predict({"user_input": "open new tab"})
    assert pred.tool_name in classes
    assert pred.raw_confidence > 0.0

    # Test crash fallback: passing corrupt/malformed payload doesn't raise exception
    pred_corrupt = runtime_model.predict({"user_input": None})
    assert pred_corrupt.raw_confidence == 0.0
    assert pred_corrupt.calibrated_confidence == 0.0


# -----------------------------------------------------------------------------
# 15. Explainability Tests
# -----------------------------------------------------------------------------


def test_attention_explainer():
    b, h, t = 1, 2, 4
    # Dummy attention tensor for 2 layers
    attn1 = np.ones((b, h, t, t), dtype=np.float64) / float(t)
    attn2 = np.ones((b, h, t, t), dtype=np.float64) / float(t)

    rollout = AttentionExplainer.compute_rollout([attn1, attn2])
    assert rollout.shape == (1, t, t)
    # Rows should sum to ~1.0
    row_sums = np.sum(rollout, axis=-1)
    assert np.allclose(row_sums, 1.0)
