"""Tests for logging configuration."""

import logging

from obsidian_note_linker.infrastructure.logging_setup import setup_logging


class TestSetupLogging:
    """Tests for setup_logging."""

    def test_configures_console_handler(self) -> None:
        setup_logging()

        root = logging.getLogger()
        handler_types = [type(h).__name__ for h in root.handlers]
        assert "StreamHandler" in handler_types

    def test_sets_custom_log_level(self) -> None:
        setup_logging(level="DEBUG")

        root = logging.getLogger()
        assert root.level == logging.DEBUG
