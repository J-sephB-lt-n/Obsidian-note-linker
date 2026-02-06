"""Configuration service — orchestrates vault configuration."""

import logging
from pathlib import Path

from obsidian_note_linker.domain.config import AppConfig, get_default_config_path
from obsidian_note_linker.infrastructure import config_store

logger = logging.getLogger(__name__)


class ConfigService:
    """Manages loading, saving, and validating vault configuration.

    Args:
        config_path: Path to the JSON config file.  Defaults to
                     ``~/.config/obsidian-linker/config.json``.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._config_path = config_path or get_default_config_path()

    def load_config(self) -> AppConfig | None:
        """Load the current configuration from disk.

        Returns:
            AppConfig if configured, None otherwise.
        """
        return config_store.load_config(config_path=self._config_path)

    def is_configured(self) -> bool:
        """Check whether a vault has been configured.

        Returns:
            True if a config file exists with a vault path.
        """
        return self.load_config() is not None

    def save_vault_path(self, vault_path: Path) -> AppConfig:
        """Validate and save a new vault path.

        The path must exist and be a directory.

        Args:
            vault_path: Path to the Obsidian vault directory.

        Returns:
            The saved AppConfig with the resolved absolute vault path.

        Raises:
            ValueError: If the path does not exist or is not a directory.
        """
        resolved = vault_path.resolve()

        if not resolved.exists():
            raise ValueError(f"Path does not exist: {resolved}")
        if not resolved.is_dir():
            raise ValueError(f"Path is not a directory: {resolved}")

        config = AppConfig(vault_path=resolved)
        config_store.save_config(config=config, config_path=self._config_path)
        logger.info("Vault path saved: %s", resolved)
        return config
