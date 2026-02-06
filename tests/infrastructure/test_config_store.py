"""Tests for configuration file storage."""

import json
from pathlib import Path

from obsidian_note_linker.domain.config import AppConfig
from obsidian_note_linker.infrastructure.config_store import load_config, save_config


class TestLoadConfig:
    """Tests for load_config."""

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        result = load_config(config_path=tmp_path / "nonexistent.json")

        assert result is None

    def test_loads_valid_config(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"vault_path": "/some/vault"}))

        result = load_config(config_path=config_path)

        assert result is not None
        assert result.vault_path == Path("/some/vault")


class TestSaveConfig:
    """Tests for save_config."""

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        config_path = tmp_path / "nested" / "dir" / "config.json"
        config = AppConfig(vault_path=Path("/some/vault"))

        save_config(config=config, config_path=config_path)

        assert config_path.exists()

    def test_writes_valid_json(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.json"
        config = AppConfig(vault_path=Path("/some/vault"))

        save_config(config=config, config_path=config_path)

        data = json.loads(config_path.read_text())
        assert data["vault_path"] == "/some/vault"


class TestConfigRoundTrip:
    """Tests for save-then-load consistency."""

    def test_round_trip_preserves_vault_path(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.json"
        original = AppConfig(vault_path=Path("/my/vault"))

        save_config(config=original, config_path=config_path)
        loaded = load_config(config_path=config_path)

        assert loaded is not None
        assert loaded.vault_path == original.vault_path
