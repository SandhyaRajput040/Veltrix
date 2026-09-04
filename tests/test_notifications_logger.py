"""
Tests for src.notifications.logger

Verifies the logger actually writes to a real rotating file (not just
"doesn't crash"), and that calling get_logger() multiple times never
attaches duplicate handlers -- which would otherwise print every log
line 2x, 3x, etc.
"""

import importlib
import logging

from src.notifications.logger import LOGGER_NAME, get_logger


def _reset_logger():
    """Remove all handlers so each test starts from a clean slate."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_get_logger_writes_a_real_log_file(tmp_path):
    _reset_logger()
    logger = get_logger(log_dir=str(tmp_path), log_file="test.log")

    logger.info("hello from the test")

    for handler in logger.handlers:
        handler.flush()

    log_path = tmp_path / "test.log"
    assert log_path.exists()
    assert "hello from the test" in log_path.read_text(encoding="utf-8")

    _reset_logger()


def test_get_logger_does_not_attach_duplicate_handlers(tmp_path):
    _reset_logger()

    logger_first_call = get_logger(log_dir=str(tmp_path), log_file="test.log")
    handler_count_after_first_call = len(logger_first_call.handlers)

    logger_second_call = get_logger(log_dir=str(tmp_path), log_file="test.log")
    handler_count_after_second_call = len(logger_second_call.handlers)

    assert handler_count_after_first_call == handler_count_after_second_call
    assert logger_first_call is logger_second_call

    _reset_logger()


def test_get_logger_creates_log_directory_if_missing(tmp_path):
    _reset_logger()
    nested_dir = tmp_path / "nested" / "logs"

    get_logger(log_dir=str(nested_dir), log_file="test.log")

    assert nested_dir.is_dir()

    _reset_logger()
