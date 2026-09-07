"""Tests proving breach-context metadata actually conditions generation.

Before this fix, DCPMGenerator.encode_context() always returned zeros
regardless of context, so `--context '{"organization": "X"}'` had zero
effect on the model. These tests train a tiny model on a multi-org dataset
and verify the learned MetadataEncoder produces context-dependent, non-zero
embeddings, and that end-to-end generation differs across contexts.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import torch

_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root))

from model import DCPMGenerator, PasswordTokenizer
from model.data import BreachContext, create_data_loaders
from model.dataset import generate_multi_org_dataset
from model.tokenizer import MetadataTokenizer
from model.train import NCGTrainer
from model import create_model
from ncg.config import InferenceConfig, ModelConfig, TrainingConfig


@pytest.fixture
def contextual_model():
    """Train a tiny model on a 3-org contextual dataset for a handful of steps."""
    # Seed weight init too (not just dataset generation) so the fixture is
    # fully reproducible across process runs -- without this, generation
    # divergence tests are at the mercy of whatever the global RNG state
    # happened to be, which previously caused an intermittent failure.
    torch.manual_seed(1234)

    passwords, metadata = generate_multi_org_dataset(
        num_per_org=60, orgs=["TechCorp", "FinanceInc", "HealthNet"], seed=7
    )

    config = ModelConfig(
        vocab_size=99, max_seq_len=16, d_model=16, n_heads=1, n_layers=1, d_ff=32,
        dropout=0.0, metadata_vocab_size=256, max_metadata_tokens=16,
    )
    net = create_model(config)
    tok = PasswordTokenizer(max_seq_len=16)
    meta_tok = MetadataTokenizer(max_metadata_tokens=16)
    meta_tok.build_vocab(metadata)

    train_cfg = TrainingConfig(batch_size=8, learning_rate=0.02, max_epochs=1, warmup_steps=1)
    train_loader, _ = create_data_loaders(
        passwords, tokenizer=tok, batch_size=8, max_seq_len=16, val_split=0.0,
        train_metadata=metadata, metadata_tokenizer=meta_tok,
    )
    trainer = NCGTrainer(net, train_cfg, torch.device("cpu"), tok, metadata_tokenizer=meta_tok)
    for i, batch in enumerate(train_loader):
        if i >= 40:
            break
        trainer.train_step(batch)
    net.eval()
    return net, tok, meta_tok, config


class TestMetadataEncoderIsLearned:
    def test_different_orgs_produce_different_nonzero_embeddings(self, contextual_model):
        net, tok, meta_tok, config = contextual_model
        gen_config = InferenceConfig(top_k=10, top_p=0.9, temperature=0.8)
        generator = DCPMGenerator(net, tok, meta_tok, inference_config=gen_config)

        emb_a = generator.encode_context(BreachContext(organization="TechCorp"))
        emb_b = generator.encode_context(BreachContext(organization="FinanceInc"))
        emb_c = generator.encode_context(BreachContext(organization="HealthNet"))

        assert not torch.all(emb_a == 0), "context embedding must not be the old all-zero stub"
        assert not torch.equal(emb_a, emb_b), "different orgs must produce different embeddings"
        assert not torch.equal(emb_b, emb_c), "different orgs must produce different embeddings"

    def test_same_org_is_deterministic(self, contextual_model):
        net, tok, meta_tok, config = contextual_model
        generator = DCPMGenerator(net, tok, meta_tok)
        emb1 = generator.encode_context(BreachContext(organization="TechCorp", year=2026))
        emb2 = generator.encode_context(BreachContext(organization="TechCorp", year=2026))
        assert torch.equal(emb1, emb2)

    def test_next_token_logits_depend_on_context(self, contextual_model):
        """Deterministic check: same prefix, different context -> different
        next-token logits. Unlike sampling from a barely-trained toy model,
        this has no seed/top-k flakiness -- it directly proves the causal
        path (context embedding -> forward() -> logits) is live."""
        net, tok, meta_tok, config = contextual_model
        prefix_ids = torch.tensor([[tok.bos_token_id]], dtype=torch.long)

        emb_a = net.encode_metadata(
            torch.tensor([meta_tok.encode_metadata({"organization": "TechCorp"})])
        )
        emb_b = net.encode_metadata(
            torch.tensor([meta_tok.encode_metadata({"organization": "FinanceInc"})])
        )

        with torch.no_grad():
            logits_a = net(prefix_ids, metadata_embeddings=emb_a)["logits"]
            logits_b = net(prefix_ids, metadata_embeddings=emb_b)["logits"]

        assert not torch.allclose(logits_a, logits_b), "next-token logits must depend on context"

    def test_generation_differs_across_contexts(self, contextual_model):
        """End-to-end sampling check, robust to any single unlucky seed: try
        several seeds and require divergence in at least one (a barely-trained
        tiny model can occasionally collapse top-k to the same path for a
        particular seed even though the underlying logits genuinely differ,
        as proven deterministically above)."""
        net, tok, meta_tok, config = contextual_model
        gen_config = InferenceConfig(top_k=15, top_p=0.9, temperature=0.9)
        generator = DCPMGenerator(net, tok, meta_tok, inference_config=gen_config)

        def gen_with(org, seed):
            torch.manual_seed(seed)
            return generator.generate_candidates(
                {"organization": org}, num_candidates=10, max_length=10
            )

        diverged = any(gen_with("TechCorp", seed) != gen_with("FinanceInc", seed) for seed in range(5))
        assert diverged, "generation must depend on context, not just seed, for at least one seed"

    def test_no_metadata_tokenizer_falls_back_to_honest_zero(self, contextual_model):
        """A model/generator with no metadata_tokenizer has no learned vocab to
        encode against -- returning zeros here is honest (context truly has no
        effect), not a hidden bug."""
        net, tok, meta_tok, config = contextual_model
        generator = DCPMGenerator(net, tok, metadata_tokenizer=None)
        emb = generator.encode_context(BreachContext(organization="TechCorp"))
        assert torch.all(emb == 0)


class TestCheckpointRoundTrip:
    def test_metadata_vocab_persists_through_checkpoint(self, contextual_model, tmp_path):
        net, tok, meta_tok, config = contextual_model
        train_cfg = TrainingConfig(batch_size=8, learning_rate=0.01, max_epochs=1)
        trainer = NCGTrainer(net, train_cfg, torch.device("cpu"), tok, metadata_tokenizer=meta_tok)

        ckpt_path = tmp_path / "model.pt"
        trainer.save_checkpoint(ckpt_path)

        reloaded = DCPMGenerator.from_checkpoint(ckpt_path, device=torch.device("cpu"))
        assert reloaded.metadata_tokenizer is not None
        assert "techcorp" in reloaded.metadata_tokenizer.word_to_id

        emb_a = reloaded.encode_context(BreachContext(organization="TechCorp"))
        emb_b = reloaded.encode_context(BreachContext(organization="FinanceInc"))
        assert not torch.equal(emb_a, emb_b)
