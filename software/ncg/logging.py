"""Logging infrastructure for NCG Framework."""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from .config import LoggingConfig


class JSONFormatter(logging.Formatter):
    """JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        if hasattr(record, "extra_fields"):
            log_obj.update(record.extra_fields)

        return json.dumps(log_obj, ensure_ascii=False)


class RichConsoleHandler(logging.Handler):
    """Rich console handler with colored output."""

    def __init__(self, level: int = logging.NOTSET):
        super().__init__(level)
        self._rich_handler: logging.Handler | None = None
        try:
            from rich.console import Console
            from rich.logging import RichHandler

            self._rich_handler = RichHandler(
                console=Console(stderr=True),
                show_time=True,
                show_level=True,
                show_path=False,
                markup=True,
                rich_tracebacks=True,
            )
        except ImportError:
            self._rich_handler = None

    def emit(self, record: logging.LogRecord) -> None:
        if self._rich_handler:
            self._rich_handler.emit(record)
        else:
            super().emit(record)


def setup_logging(config: LoggingConfig) -> logging.Logger:
    """Configure application logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.level.upper()))

    root_logger.handlers.clear()

    if config.format.lower() == "json":
        formatter: logging.Formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    if config.output.lower() == "stdout":
        handler: logging.Handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    elif config.output.lower() == "stderr":
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)
    elif config.output.lower() == "rich":
        handler = RichConsoleHandler()
        root_logger.addHandler(handler)

    if config.file_path:
        file_path = Path(config.file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            file_path,
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    logging.getLogger("torch").setLevel(logging.WARNING)
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get logger instance."""
    return logging.getLogger(name)


class LogContext:
    """Context manager for adding extra fields to log records."""

    def __init__(self, **extra_fields: Any):
        self.extra_fields = extra_fields
        self.old_factory = logging.getLogRecordFactory()

    def __enter__(self) -> LogContext:
        def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = self.old_factory(*args, **kwargs)
            record.extra_fields = self.extra_fields
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, *args: Any) -> None:
        logging.setLogRecordFactory(self.old_factory)


F = TypeVar("F", bound=Callable[..., Any])


def log_function_call(logger: logging.Logger, level: int = logging.DEBUG) -> Callable[[F], F]:
    """Decorator to log function calls."""

    def decorator(func: F) -> F:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.log(
                level,
                f"Calling {func.__name__}",
                extra={
                    "extra_fields": {
                        "function": func.__name__,
                        "args": str(args)[:200],
                        "kwargs": str(kwargs)[:200],
                    }
                },
            )
            try:
                result = func(*args, **kwargs)
                logger.log(level, f"Completed {func.__name__}")
                return result
            except Exception as e:
                logger.exception(f"Failed {func.__name__}: {e}")
                raise

        return wrapper  # type: ignore[return-value]

    return decorator
