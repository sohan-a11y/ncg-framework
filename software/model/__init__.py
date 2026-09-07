"""NCG Model Package - Quantized Transformer for Cryptanalysis."""

from __future__ import annotations

from .data import (
    BreachContext,
    PasswordDataset,
    create_data_loaders,
    generate_synthetic_metadata,
    load_password_list,
    load_rockyou,
)
from .export import (
    export_for_deployment,
    export_to_onnx,
    export_to_torchscript,
    export_tokenizer,
    quantize_model_for_export,
)
from .inference import DCPMGenerator, load_generator
from .model import NCGTransformer, QuantizedLinear, TransformerBlock, create_model
from .tokenizer import CHAR_TO_ID, ID_TO_CHAR, VOCAB_SIZE, MetadataTokenizer, PasswordTokenizer
from .train import NCGTrainer, create_scheduler, train

__all__ = [
    # Tokenizer
    "PasswordTokenizer",
    "MetadataTokenizer",
    "VOCAB_SIZE",
    "CHAR_TO_ID",
    "ID_TO_CHAR",
    # Data
    "BreachContext",
    "PasswordDataset",
    "load_password_list",
    "load_rockyou",
    "create_data_loaders",
    "generate_synthetic_metadata",
    # Model
    "NCGTransformer",
    "QuantizedLinear",
    "create_model",
    "TransformerBlock",
    # Training
    "NCGTrainer",
    "train",
    "create_scheduler",
    # Inference
    "DCPMGenerator",
    "load_generator",
    # Export
    "export_to_onnx",
    "export_to_torchscript",
    "export_tokenizer",
    "export_for_deployment",
    "quantize_model_for_export",
]
