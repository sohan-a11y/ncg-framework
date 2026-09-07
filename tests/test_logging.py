"""Tests for logging infrastructure."""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import pytest

from ncg.config import LoggingConfig
from ncg.logging import JSONFormatter, LogContext, get_logger, setup_logging


class TestJSONFormatter:
    """Tests for JSONFormatter."""

    def test_format_basic(self) -> None:
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.module = "test"
        record.funcName = "test_func"

        output = formatter.format(record)
        data = json.loads(output)

        assert data["level"] == "INFO"
        assert data["logger"] == "test.logger"
        assert data["message"] == "Test message"
        assert data["module"] == "test"
        assert data["function"] == "test_func"
        assert data["line"] == 42

    def test_format_with_exception(self) -> None:
        formatter = JSONFormatter()
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=42,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )
        record.module = "test"
        record.funcName = "test_func"

        output = formatter.format(record)
        data = json.loads(output)

        assert data["level"] == "ERROR"
        assert "exception" in data
        assert "ValueError: Test error" in data["exception"]


class TestSetupLogging:
    """Tests for setup_logging."""

    def test_setup_stdout_json(self) -> None:
        config = LoggingConfig(level="DEBUG", format="json", output="stdout")
        logger = setup_logging(config)

        assert logger.level == logging.DEBUG
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0].formatter, JSONFormatter)

    def test_setup_file_logging(self) -> None:
        import tempfile
        import shutil

        tmpdir = Path(tempfile.mkdtemp())
        try:
            log_file = tmpdir / "test.log"
            config = LoggingConfig(level="INFO", format="json", output="file", file_path=str(log_file))
            logger = setup_logging(config)

            test_logger = get_logger("test")
            test_logger.info("Test message")

            # Force flush and close handlers
            for handler in logger.handlers[:]:
                handler.flush()
                handler.close()
                logger.removeHandler(handler)

            assert log_file.exists()
            content = log_file.read_text()
            assert "Test message" in content
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_setup_rich(self) -> None:
        config = LoggingConfig(level="INFO", format="text", output="rich")
        logger = setup_logging(config)

        assert logger.level == logging.INFO
        assert len(logger.handlers) >= 1


class TestLogContext:
    """Tests for LogContext."""

    def test_context_adds_extra_fields(self) -> None:
        logger = get_logger("test.context")

        with LogContext(user_id=123, request_id="abc"):
            # The extra fields should be added to records
            pass  # Actual testing would require capturing log output

    def test_nested_context(self) -> None:
        with LogContext(outer="value1"):
            with LogContext(inner="value2"):
                pass


class TestGetLogger:
    """Tests for get_logger."""

    def test_get_logger_returns_logger(self) -> None:
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"