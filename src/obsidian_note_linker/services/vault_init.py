"""Vault state initialisation service."""

import logging

from sqlalchemy.engine import Engine

import obsidian_note_linker.infrastructure.models  # noqa: F401  — register tables
from obsidian_note_linker.domain.config import AppConfig
from obsidian_note_linker.infrastructure.database import create_db_engine

logger = logging.getLogger(__name__)


def initialize_vault_state(config: AppConfig) -> Engine:
    """Ensure the vault state directory and database are ready.

    Creates the ``.obsidian-linker/`` directory tree inside the vault
    and initialises the SQLite database with WAL mode.

    Args:
        config: Application configuration with the vault path.

    Returns:
        The configured database engine.
    """
    logger.info("Initialising vault state for %s", config.vault_path)
    config.vault_state_dir.mkdir(parents=True, exist_ok=True)
    engine = create_db_engine(db_path=config.db_path)
    logger.info("Vault state ready: db=%s", config.db_path)
    return engine
