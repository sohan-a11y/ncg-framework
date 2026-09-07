"""End-to-end integration tests for the NCG framework.

These tests verify that the trained software model produces candidates whose
SHA-256 hashes can be verified through the hardware-like pipeline.
This is the critical link between Phase 1 (software model) and Phase 2/3
(hardware verification).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
import torch

# Add project root to path
_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root))

from hardware.python_sim import NcgHardwareSim, sha256_hash
from model import DCPMGenerator, PasswordTokenizer
from model.data import BreachContext
from ncg.config import ModelConfig, InferenceConfig


class TestModelToHashPipeline:
    """Test that model-generated candidates can be hashed and verified."""

    @pytest.fixture
    def small_trained_model(self, tmp_path):
        """Create a small trained model for testing.

        We don't load a real checkpoint (those are large); instead we
        train a tiny model for a few iterations to get a model that
        produces something. This tests the full pipeline end-to-end.
        """
        from model.train import NCGTrainer
        from model import create_model
        from model.tokenizer import PasswordTokenizer
        from model.data import create_data_loaders

        # Create very small model for fast training
        config = ModelConfig(
            vocab_size=99, max_seq_len=16, d_model=16,
            n_heads=1, n_layers=1, d_ff=32, dropout=0.0
        )
        net = create_model(config)
        tok = PasswordTokenizer(max_seq_len=16)

        # Tiny training set with a clear pattern
        passwords = ["admin", "admin1", "test", "test1", "password"]
        from ncg.config import TrainingConfig
        train_cfg = TrainingConfig(
            batch_size=2, learning_rate=0.01, max_epochs=5,
            warmup_steps=1, gradient_clip=1.0
        )
        train_loader, _ = create_data_loaders(
            passwords, tokenizer=tok, batch_size=2, max_seq_len=16, val_split=0.0
        )
        trainer = NCGTrainer(net, train_cfg, torch.device("cpu"), tok)
        # Just 5 batches of training
        for i, batch in enumerate(train_loader):
            if i >= 5:
                break
            trainer.train_step(batch)
        net.eval()
        return net, tok, config

    def test_model_candidates_have_valid_hashes(self, small_trained_model):
        """Generated candidates should produce valid SHA-256 hashes."""
        net, tok, config = small_trained_model

        gen_config = InferenceConfig(top_k=10, top_p=0.9, temperature=0.8)
        generator = DCPMGenerator(net, tok, inference_config=gen_config)

        context = BreachContext(organization="admin")
        # Use max_length=8 since our small model has max_seq_len=16
        candidates = generator.generate_candidates(
            context, num_candidates=20, max_length=8
        )

        assert len(candidates) > 0, "No candidates generated"

        for cand in candidates:
            # Empty string would be invalid
            assert len(cand) > 0, f"Empty candidate: {cand!r}"
            # Hash should be computable
            h = hashlib.sha256(cand.encode()).hexdigest()
            assert len(h) == 64  # SHA-256 = 32 bytes = 64 hex chars

    def test_pipeline_can_find_known_password(self, small_trained_model):
        """Build a DCPM with a known password, verify pipeline finds it.

        The DCPM walk always produces candidate_len-byte candidates.
        The target hash is the SHA-256 of that candidate_len-byte string.
        For candidate 0, byte_sel = (0+pos)%8 = pos%8.
        To produce "admin" followed by zeros:
        - row 0 byte 0 = 'a', row 1 byte 1 = 'd', row 2 byte 2 = 'm', ...
        - remaining rows all zeros
        """
        net, tok, config = small_trained_model

        # The candidate the pipeline produces is candidate_len bytes
        sim = NcgHardwareSim(candidate_len=16)
        target_candidate = b"admin" + b"\x00" * 11  # 16 bytes total
        target_hash = hashlib.sha256(target_candidate).digest()

        # Construct DCPM so candidate 0 == target_candidate
        # For candidate 0, each position pos selects byte pos%8 from its row
        dcmp_rows = []
        for pos in range(16):
            row = bytearray(8)
            if pos < 5:  # "admin" is 5 chars
                row[pos % 8] = target_candidate[pos]
            # else: all zeros (for pos 5..15, byte pos%8 is 5..7 which are 0)
            dcmp_rows.append(bytes(row))

        found, idx, match, cands = sim.run_ncg_pipeline(
            dcmp_rows, target_hash, num_candidates=4
        )
        assert found is True
        assert cands[0] == target_candidate
        assert match == target_hash

    def test_realistic_scenario_small_candidates(self, small_trained_model):
        """Simulate a realistic small search: 100 candidates, looking for a hash."""
        net, tok, config = small_trained_model

        gen_config = InferenceConfig(top_k=20, top_p=0.9, temperature=0.7)
        generator = DCPMGenerator(net, tok, inference_config=gen_config)

        context = BreachContext(organization="test")
        # Use max_length=8 to match our small model's max_seq_len=16
        candidates = generator.generate_candidates(
            context, num_candidates=100, max_length=8
        )

        # Pick a random target (simulating a real hash to crack)
        target_candidate = candidates[0]
        target_hash = hashlib.sha256(target_candidate.encode()).digest()

        # Run a mini-version of the hardware pipeline on these candidates
        sim = NcgHardwareSim()
        found, idx, match = sim.run_hashing_array(
            [c.encode() for c in candidates],
            target_hash
        )
        # The first candidate should be the first one generated, so the
        # target was the first one hashed
        assert found is True
        assert idx == 0

    def test_no_match_returns_not_found(self, small_trained_model):
        """Pipeline with a target that nothing matches should return not found."""
        net, tok, config = small_trained_model
        sim = NcgHardwareSim(candidate_len=16)

        # DCPM produces only "admin"
        dcmp = [b"admin\x00\x00\x00"] + [b"\x00" * 8] * 15

        # Target is "qwerty" (not in DCPM)
        target = hashlib.sha256(b"qwerty").digest()

        found, idx, _ = sim.run_hashing_array(
            sim.run_dcpm(dcmp, num_candidates=10), target
        )
        assert found is False


class TestHashingPerformance:
    """Performance and throughput sanity tests."""

    def test_hash_throughput(self):
        """Verify hashing many candidates completes in reasonable time."""
        import time

        sim = NcgHardwareSim()
        # Generate 1000 random 8-byte candidates
        import os
        candidates = [os.urandom(8) for _ in range(1000)]
        target = os.urandom(32)  # random target (no match)

        start = time.time()
        found, idx, match = sim.run_hashing_array(candidates, target)
        elapsed = time.time() - start

        # 1000 SHA-256 hashes should take < 1 second on modern hardware
        assert elapsed < 5.0, f"Hashing 1000 candidates took {elapsed:.2f}s"
        assert found is False  # random target shouldn't match

    def test_dcpm_generation_throughput(self):
        """Verify DCPM walk can generate many candidates quickly."""
        import time

        sim = NcgHardwareSim(candidate_len=16)
        dcmp = [bytes(range(8)) for _ in range(16)]

        start = time.time()
        candidates = sim.run_dcpm(dcmp, num_candidates=10000)
        elapsed = time.time() - start

        assert len(candidates) == 10000
        # 10K candidate generation should be sub-second
        assert elapsed < 2.0, f"Generating 10K candidates took {elapsed:.2f}s"