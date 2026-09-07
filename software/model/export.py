"""Model export utilities for NCG Framework."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import torch

from .model import NCGTransformer
from .tokenizer import PasswordTokenizer

logger = logging.getLogger(__name__)


def _get_max_seq_len(model: torch.nn.Module) -> int:
    """Extract max_seq_len from model config."""
    max_seq_len = getattr(getattr(model, "config", None), "max_seq_len", None)
    if max_seq_len is None:
        max_seq_len = getattr(model, "max_seq_len", 64)
    return max_seq_len  # type: ignore[return-value]


def _create_dummy_inputs(
    model: torch.nn.Module, input_shape: tuple[int, int] | None = None
) -> tuple[torch.Tensor, torch.Tensor]:
    """Create dummy inputs for model export."""
    max_seq_len = _get_max_seq_len(model)
    if input_shape is None:
        input_shape = (1, max_seq_len)
    vocab_size = getattr(model, "vocab_size", 99)
    dummy_input = torch.randint(0, vocab_size, input_shape, dtype=torch.long)
    dummy_mask = torch.ones_like(dummy_input)
    return dummy_input, dummy_mask


class _OnnxWrapper(torch.nn.Module):
    """Wraps NCGTransformer so forward() returns a tuple (ONNX-compatible, no dict outputs)."""

    def __init__(self, model: torch.nn.Module):
        super().__init__()
        self.inner = model

    def forward(
        self, input_ids: torch.Tensor, attention_mask: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        out = self.inner(input_ids, attention_mask=attention_mask)
        return out["logits"], out["hidden_states"]


def export_to_onnx(
    model: torch.nn.Module,
    tokenizer: PasswordTokenizer,
    output_path: str | Path,
    input_shape: tuple[int, int] | None = None,
    opset_version: int = 17,
    dynamic_axes: dict | None = None,
) -> None:
    """Export model to ONNX format."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    model.eval()

    vocab_size = getattr(getattr(model, "config", None), "vocab_size", 99)
    max_seq_len = _get_max_seq_len(model)
    if input_shape is None:
        input_shape = (1, max_seq_len)
    dummy_input = torch.randint(4, vocab_size, input_shape, dtype=torch.long)
    dummy_mask = torch.ones_like(dummy_input)

    if dynamic_axes is None:
        dynamic_axes = {
            "input_ids": {0: "batch", 1: "sequence"},
            "attention_mask": {0: "batch", 1: "sequence"},
            "logits": {0: "batch", 1: "sequence"},
            "hidden_states": {0: "batch", 1: "sequence"},
        }

    logger.info("Exporting to ONNX: %s", output_path)

    wrapped = _OnnxWrapper(model)
    wrapped.eval()

    torch.onnx.export(
        wrapped,
        (dummy_input, dummy_mask),
        output_path,
        export_params=True,
        opset_version=opset_version,
        do_constant_folding=True,
        input_names=["input_ids", "attention_mask"],
        output_names=["logits", "hidden_states"],
        dynamic_axes=dynamic_axes,
        verbose=False,
        dynamo=False,  # legacy exporter: handles dict-free wrapper reliably
    )

    logger.info("ONNX export completed: %s", output_path)


def export_to_torchscript(
    model: torch.nn.Module,
    output_path: str | Path,
    input_shape: tuple[int, int] | None = None,
    method: str = "trace",
) -> None:
    """Export model to TorchScript format."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    model.eval()

    dummy_input, dummy_mask = _create_dummy_inputs(model, input_shape)

    logger.info("Exporting to TorchScript (%s): %s", method, output_path)

    if method == "trace":
        # Use strict=False to allow dict outputs
        scripted = torch.jit.trace(model, (dummy_input, dummy_mask), strict=False)
    elif method == "script":
        scripted = torch.jit.script(model)
    else:
        raise ValueError(f"Unknown method: {method}. Use 'trace' or 'script'.")

    scripted.save(str(output_path))
    logger.info("TorchScript export completed: %s", output_path)


def export_tokenizer(
    tokenizer: PasswordTokenizer,
    output_dir: str | Path,
) -> None:
    """Export tokenizer configuration."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tokenizer.save_pretrained(output_dir)

    # Also save vocab mapping for reference
    from .tokenizer import ID_TO_CHAR

    vocab_file = output_dir / "vocab.json"
    with open(vocab_file, "w") as f:
        json.dump(
            {
                "char_to_id": {ch: i for i, ch in ID_TO_CHAR.items() if i >= 4},
                "special_tokens": {
                    "pad": tokenizer.pad_token_id,
                    "bos": tokenizer.bos_token_id,
                    "eos": tokenizer.eos_token_id,
                    "unk": tokenizer.unk_token_id,
                },
                "max_seq_len": tokenizer.max_seq_len,
                "vocab_size": tokenizer.vocab_size,
            },
            f,
            indent=2,
        )

    logger.info("Tokenizer exported to: %s", output_dir)


def quantize_model_for_export(
    model: NCGTransformer,
    quantization: str = "int8",
) -> torch.nn.Module:
    """Apply quantization for export."""
    if quantization == "int8":
        # Dynamic quantization for linear layers
        quantized = torch.quantization.quantize_dynamic(
            model,
            {torch.nn.Linear},
            dtype=torch.qint8,
        )
        return quantized  # type: ignore
    elif quantization == "int4":
        # INT4 quantization (custom)
        model.quantize_model()
        return model
    else:
        raise ValueError(f"Unsupported quantization: {quantization}")


def export_for_deployment(
    model: NCGTransformer,
    tokenizer: PasswordTokenizer,
    output_dir: str | Path,
    formats: list[str] | None = None,
    quantization: str | None = None,
) -> dict[str, str]:
    """Export model and tokenizer for deployment."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    exported_files = {}

    # Export tokenizer
    export_tokenizer(tokenizer, output_dir / "tokenizer")
    exported_files["tokenizer"] = str(output_dir / "tokenizer")

    # Apply quantization if requested
    export_model: torch.nn.Module = model
    if quantization:
        export_model = quantize_model_for_export(model, quantization)

    # Default formats
    if formats is None:
        formats = ["onnx", "torchscript"]

    # Export to each format
    if "onnx" in formats:
        onnx_path = output_dir / "model.onnx"
        export_to_onnx(export_model, tokenizer, onnx_path)
        exported_files["onnx"] = str(onnx_path)

    if "torchscript" in formats:
        ts_path = output_dir / "model.ts"
        export_to_torchscript(export_model, ts_path)
        exported_files["torchscript"] = str(ts_path)

    # Save model config
    config_path = output_dir / "model_config.json"
    with open(config_path, "w") as f:
        json.dump(
            {
                "d_model": model.d_model,
                "n_heads": model.config.n_heads,
                "n_layers": model.config.n_layers,
                "vocab_size": model.vocab_size,
                "max_seq_len": model.max_seq_len,
                "quantization": quantization,
            },
            f,
            indent=2,
        )
    exported_files["config"] = str(config_path)

    logger.info("Deployment export completed to: %s", output_dir)
    return exported_files
