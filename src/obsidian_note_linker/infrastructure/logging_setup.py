"""Logging configuration using YAML."""

import logging
import logging.config
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "logging.yaml"


def setup_logging(level: str = "INFO") -> None:
    """Configure logging from the bundled YAML config (console output only).

    Args:
        level: Root log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    with open(_DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    config["root"]["level"] = level

    logging.config.dictConfig(config)
    logger.debug("Logging configured (level=%s)", level)
