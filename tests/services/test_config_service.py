"""Tests for the configuration service."""

from pathlib import Path

import pytest

from obsidian_note_linker.services.config_service import ConfigService


class TestIsConfigured:
    """Tests for ConfigService.is_configured."""

    def test_false_when_no_config_file(self, tmp_path: Path) -> None:
        svc = ConfigService(config_path=tmp_path / "config.json")

        assert svc.is_configured() is False

    def test_true_after_saving_vault_path(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        svc = ConfigService(config_path=tmp_path / "config.json")

        svc.save_vault_path(vault_path=vault)

        assert svc.is_configured() is True


class TestLoadConfig:
    """Tests for ConfigService.load_config."""

    def test_returns_none_when_not_configured(self, tmp_path: Path) -> None:
        svc = ConfigService(config_path=tmp_path / "config.json")

        assert svc.load_config() is None

    def test_returns_config_after_save(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        svc = ConfigService(config_path=tmp_path / "config.json")

        svc.save_vault_path(vault_path=vault)
        result = svc.load_config()

        assert result is not None
        assert result.vault_path == vault.resolve()


class TestSaveVaultPath:
    """Tests for ConfigService.save_vault_path."""

    def test_raises_when_path_does_not_exist(self, tmp_path: Path) -> None:
        svc = ConfigService(config_path=tmp_path / "config.json")

        with pytest.raises(ValueError, match="does not exist"):
            svc.save_vault_path(vault_path=tmp_path / "nonexistent")

    def test_raises_when_path_is_file(self, tmp_path: Path) -> None:
        file_path = tmp_path / "not_a_dir.txt"
        file_path.write_text("hello")
        svc = ConfigService(config_path=tmp_path / "config.json")

        with pytest.raises(ValueError, match="not a directory"):
            svc.save_vault_path(vault_path=file_path)

    def test_saves_resolved_absolute_path(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        svc = ConfigService(config_path=tmp_path / "config.json")

        config = svc.save_vault_path(vault_path=vault)

        assert config.vault_path == vault.resolve()
        assert config.vault_path.is_absolute()
