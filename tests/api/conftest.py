"""API test fixtures."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obsidian_note_linker.api.app import create_app
from obsidian_note_linker.services.config_service import ConfigService


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Return a temporary config file path."""
    return tmp_path / "config" / "config.json"


@pytest.fixture
def client_no_config(config_path: Path) -> TestClient:
    """Test client for an app with no vault configured."""
    app = create_app(config_path=config_path)
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def client_with_config(tmp_path: Path, config_path: Path) -> TestClient:
    """Test client for an app with a vault pre-configured."""
    vault = tmp_path / "vault"
    vault.mkdir()
    svc = ConfigService(config_path=config_path)
    svc.save_vault_path(vault_path=vault)
    app = create_app(config_path=config_path)
    return TestClient(app, follow_redirects=False)
