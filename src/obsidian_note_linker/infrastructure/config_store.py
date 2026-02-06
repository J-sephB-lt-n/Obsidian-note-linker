"""Persistent storage for application configuration."""

import json
import logging
from pathlib import Path

from obsidian_note_linker.domain.config import AppConfig

logger = logging.getLogger(__name__)


def load_config(config_path: Path) -> AppConfig | None:
    """Load application configuration from a JSON file.

    Args:
        config_path: Path to the configuration JSON file.

    Returns:
        AppConfig if the file exists and is valid, None otherwise.
    """
    if not config_path.exists():
        logger.debug("No config file found at %s", config_path)
        return None

    data = json.loads(config_path.read_text(encoding="utf-8"))
    vault_path = Path(data["vault_path"])
    logger.info("Loaded config with vault path: %s", vault_path)
    return AppConfig(vault_path=vault_path)


def save_config(config: AppConfig, config_path: Path) -> None:
    """Save application configuration to a JSON file.

    Creates parent directories if they don't exist.

    Args:
        config: The application configuration to save.
        config_path: Path to write the configuration JSON file.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"vault_path": str(config.vault_path)}
    config_path.write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("Saved config to %s", config_path)
