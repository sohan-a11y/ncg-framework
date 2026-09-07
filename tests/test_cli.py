"""Tests for CLI."""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from ncg.cli import cli


class TestCLI:
    """Tests for CLI commands."""

    def setup_method(self) -> None:
        self.runner = CliRunner()

    def test_version(self) -> None:
        result = self.runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "NCG Framework" in result.output
        assert "0.1.0" in result.output

    def test_help(self) -> None:
        result = self.runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Neuromorphic Cryptanalytic Generator" in result.output

    def test_model_train_help(self) -> None:
        result = self.runner.invoke(cli, ["model", "train", "--help"])
        assert result.exit_code == 0
        assert "Training data path" in result.output

    def test_model_generate_help(self) -> None:
        result = self.runner.invoke(cli, ["model", "generate", "--help"])
        assert result.exit_code == 0
        assert "Target context" in result.output

    def test_model_export_help(self) -> None:
        result = self.runner.invoke(cli, ["model", "export", "--help"])
        assert result.exit_code == 0
        assert "Export format" in result.output

    def test_hardware_simulate_help(self) -> None:
        result = self.runner.invoke(cli, ["hardware", "simulate", "--help"])
        assert result.exit_code == 0
        assert "RTL design path" in result.output

    def test_hardware_synthesize_help(self) -> None:
        result = self.runner.invoke(cli, ["hardware", "synthesize", "--help"])
        assert result.exit_code == 0
        assert "Target device" in result.output

    def test_doctor(self) -> None:
        result = self.runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "NCG Framework System Check" in result.output

    def test_invalid_command(self) -> None:
        result = self.runner.invoke(cli, ["invalid-command"])
        assert result.exit_code != 0

    def test_model_train_missing_args(self) -> None:
        result = self.runner.invoke(cli, ["model", "train"])
        assert result.exit_code != 0
        assert "Missing option" in result.output