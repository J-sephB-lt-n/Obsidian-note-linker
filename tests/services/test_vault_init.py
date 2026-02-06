"""Tests for vault state initialisation."""

from pathlib import Path

from obsidian_note_linker.domain.config import AppConfig
from obsidian_note_linker.services.vault_init import initialize_vault_state


class TestInitializeVaultState:
    """Tests for initialize_vault_state."""

    def test_creates_vault_state_directory(self, vault_path: Path) -> None:
        config = AppConfig(vault_path=vault_path)

        initialize_vault_state(config=config)

        assert config.vault_state_dir.exists()
        assert config.vault_state_dir.is_dir()

    def test_creates_database_file(self, vault_path: Path) -> None:
        config = AppConfig(vault_path=vault_path)

        initialize_vault_state(config=config)

        assert config.db_path.exists()

    def test_returns_working_engine(self, vault_path: Path) -> None:
        config = AppConfig(vault_path=vault_path)

        engine = initialize_vault_state(config=config)

        assert engine is not None
