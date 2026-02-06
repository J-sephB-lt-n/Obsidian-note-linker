"""Tests for domain configuration models."""

from pathlib import Path

from obsidian_note_linker.domain.config import (
    AppConfig,
    get_default_config_dir,
    get_default_config_path,
)


class TestAppConfig:
    """Tests for AppConfig dataclass properties."""

    def test_vault_state_dir(self, tmp_path: Path) -> None:
        config = AppConfig(vault_path=tmp_path / "vault")

        assert config.vault_state_dir == tmp_path / "vault" / ".obsidian-linker"

    def test_db_path(self, tmp_path: Path) -> None:
        config = AppConfig(vault_path=tmp_path / "vault")

        assert config.db_path == tmp_path / "vault" / ".obsidian-linker" / "state.db"

    def test_is_frozen(self, tmp_path: Path) -> None:
        config = AppConfig(vault_path=tmp_path / "vault")

        with __import__("pytest").raises(AttributeError):
            config.vault_path = tmp_path / "other"  # type: ignore[misc]


class TestConfigPaths:
    """Tests for configuration path utility functions."""

    def test_default_config_dir_is_under_home(self) -> None:
        result = get_default_config_dir()

        assert result == Path.home() / ".config" / "obsidian-linker"

    def test_default_config_path_is_json_file(self) -> None:
        result = get_default_config_path()

        assert result == Path.home() / ".config" / "obsidian-linker" / "config.json"
        assert result.suffix == ".json"
