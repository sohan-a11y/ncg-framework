"""Tests for configuration system."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from ncg.config import Config, ModelConfig, TrainingConfig, load_config


class TestModelConfig:
    """Tests for ModelConfig."""

    def test_defaults(self) -> None:
        cfg = ModelConfig()
        assert cfg.vocab_size == 99
        assert cfg.max_seq_len == 64
        assert cfg.d_model == 256
        assert cfg.n_heads == 8
        assert cfg.quantization == "int4"

    def test_custom_values(self) -> None:
        cfg = ModelConfig(vocab_size=128, d_model=512, n_layers=12)
        assert cfg.vocab_size == 128
        assert cfg.d_model == 512
        assert cfg.n_layers == 12


class TestTrainingConfig:
    """Tests for TrainingConfig."""

    def test_defaults(self) -> None:
        cfg = TrainingConfig()
        assert cfg.batch_size == 32
        assert cfg.learning_rate == 3e-4
        assert cfg.max_epochs == 100
        assert cfg.mixed_precision is True
        assert cfg.quantization_aware is True

    def test_custom_values(self) -> None:
        cfg = TrainingConfig(batch_size=64, learning_rate=1e-4, max_epochs=50)
        assert cfg.batch_size == 64
        assert cfg.learning_rate == 1e-4
        assert cfg.max_epochs == 50


class TestConfig:
    """Tests for root Config."""

    def test_default_config(self) -> None:
        cfg = Config()
        assert isinstance(cfg.model, ModelConfig)
        assert isinstance(cfg.training, TrainingConfig)
        assert cfg.model.vocab_size == 99
        assert cfg.training.batch_size == 32

    def test_from_yaml(self) -> None:
        data = {
            "model": {"vocab_size": 128, "d_model": 512},
            "training": {"batch_size": 64, "learning_rate": 1e-4},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            path = f.name

        try:
            cfg = Config.from_yaml(path)
            assert cfg.model.vocab_size == 128
            assert cfg.model.d_model == 512
            assert cfg.training.batch_size == 64
            assert cfg.training.learning_rate == 1e-4
        finally:
            Path(path).unlink()

    def test_to_yaml(self) -> None:
        cfg = Config()
        cfg.model.vocab_size = 128
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            path = f.name

        try:
            cfg.to_yaml(path)
            with open(path) as f:
                loaded = yaml.safe_load(f)
            assert loaded["model"]["vocab_size"] == 128
        finally:
            Path(path).unlink()

    def test_merge(self) -> None:
        base = Config()
        base.model.vocab_size = 96
        base.training.batch_size = 32

        override = Config()
        override.model.vocab_size = 128
        override.training.learning_rate = 1e-3

        merged = base.merge(override)
        assert merged.model.vocab_size == 128
        assert merged.training.batch_size == 32
        assert merged.training.learning_rate == 1e-3


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_default(self) -> None:
        cfg = load_config()
        assert isinstance(cfg, Config)

    def test_load_from_file(self) -> None:
        data = {"model": {"vocab_size": 256}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            path = f.name

        try:
            cfg = load_config(path)
            assert cfg.model.vocab_size == 256
        finally:
            Path(path).unlink()