"""Configuration system for NCG Framework."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class ModelConfig(BaseModel):
    """Transformer model configuration."""

    vocab_size: int = 99
    max_seq_len: int = 64
    d_model: int = 256
    n_heads: int = 8
    n_layers: int = 6
    d_ff: int = 1024
    dropout: float = 0.1
    quantization: str = "int4"
    pad_token_id: int = 0
    bos_token_id: int = 1
    eos_token_id: int = 2
    unk_token_id: int = 3
    metadata_vocab_size: int = 2048
    max_metadata_tokens: int = 32


class TrainingConfig(BaseModel):
    """Training configuration."""

    batch_size: int = 32
    learning_rate: float = 3e-4
    weight_decay: float = 0.01
    max_epochs: int = 100
    warmup_steps: int = 1000
    gradient_clip: float = 1.0
    mixed_precision: bool = True
    quantization_aware: bool = True
    distillation: bool = False
    teacher_model_path: str | None = None


class InferenceConfig(BaseModel):
    """Inference configuration."""

    top_k: int = 50
    top_p: float = 0.9
    temperature: float = 1.0
    num_beams: int = 4
    max_new_tokens: int = 64
    do_sample: bool = True


class HardwareConfig(BaseModel):
    """Hardware/FPGA configuration."""

    target_device: str = "alveo_u50"
    clock_mhz: int = 200
    hash_engines: int = 1024
    logic_allocation_hash: float = 0.6
    logic_allocation_ai: float = 0.3
    logic_allocation_ctrl: float = 0.1
    pcie_gen: int = 5
    pcie_lanes: int = 16
    hbm_channels: int = 2


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"
    output: str = "stdout"
    file_path: str | None = None
    max_bytes: int = 10_485_760
    backup_count: int = 5


class Config(BaseModel):
    """Root configuration."""

    model: ModelConfig = Field(default_factory=ModelConfig)
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    inference: InferenceConfig = Field(default_factory=InferenceConfig)
    hardware: HardwareConfig = Field(default_factory=HardwareConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @field_validator("logging", mode="before")
    @classmethod
    def validate_logging(cls, v: Any) -> Any:
        if isinstance(v, dict):
            return LoggingConfig(**v)
        return v

    @classmethod
    def from_yaml(cls, path: str | Path) -> Config:
        """Load configuration from YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    @classmethod
    def from_env(cls, prefix: str = "NCG_") -> dict[str, Any]:
        """Load configuration from environment variables as a dict."""
        data: dict[str, Any] = {}
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix) :].lower()
                keys = config_key.split("__")
                d = data
                for k in keys[:-1]:
                    d = d.setdefault(k, {})
                d[keys[-1]] = value
        return data

    def to_yaml(self, path: str | Path) -> None:
        """Save configuration to YAML file."""
        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False, sort_keys=False)

    def merge(self, other: Config | dict[str, Any]) -> Config:
        """Merge with another config or dict (other takes precedence)."""
        merged = self.model_dump()
        other_dict = other.model_dump() if isinstance(other, Config) else other

        def deep_merge(base: dict, override: dict) -> dict:
            for key, value in override.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    base[key] = deep_merge(base[key], value)
                else:
                    base[key] = value
            return base

        merged_dict = deep_merge(merged, other_dict)
        return Config.model_validate(merged_dict)


DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config.yaml"


def load_config(config_path: str | Path | None = None) -> Config:
    """Load configuration from file, environment, or defaults."""
    config = Config()

    if config_path:
        config = config.merge(Config.from_yaml(config_path))
    elif DEFAULT_CONFIG_PATH.exists():
        config = config.merge(Config.from_yaml(DEFAULT_CONFIG_PATH))

    env_data = Config.from_env()
    if env_data:
        config = config.merge(env_data)

    return config
