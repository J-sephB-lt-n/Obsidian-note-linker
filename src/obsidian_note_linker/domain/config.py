"""Application configuration models and path constants."""

from dataclasses import dataclass
from pathlib import Path

CONFIG_DIR_NAME = "obsidian-linker"
VAULT_STATE_DIR_NAME = ".obsidian-linker"
DB_FILENAME = "state.db"
CONFIG_FILENAME = "config.json"


@dataclass(frozen=True)
class AppConfig:
    """Immutable application configuration containing the vault path.

    Provides computed properties for derived paths (state directory,
    database file) based on the vault path.
    """

    vault_path: Path

    @property
    def vault_state_dir(self) -> Path:
        """Path to the vault's state directory (<vault>/.obsidian-linker/)."""
        return self.vault_path / VAULT_STATE_DIR_NAME

    @property
    def db_path(self) -> Path:
        """Path to the SQLite database file."""
        return self.vault_state_dir / DB_FILENAME


def get_default_config_dir() -> Path:
    """Return the default configuration directory (~/.config/obsidian-linker/).

    Returns:
        Path to the configuration directory.
    """
    return Path.home() / ".config" / CONFIG_DIR_NAME


def get_default_config_path() -> Path:
    """Return the default configuration file path.

    Returns:
        Path to config.json within the configuration directory.
    """
    return get_default_config_dir() / CONFIG_FILENAME
