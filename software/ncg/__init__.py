"""NCG Framework - Neuromorphic Cryptanalytic Generator."""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "NCG Contributors"
__license__ = "Apache-2.0"

from .config import Config, load_config
from .logging import get_logger, setup_logging

__all__ = [
    "Config",
    "load_config",
    "get_logger",
    "setup_logging",
]
