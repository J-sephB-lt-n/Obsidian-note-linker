"""Shared test fixtures."""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from obsidian_note_linker.domain.config import AppConfig


@pytest.fixture
def vault_path(tmp_path: Path) -> Path:
    """Create and return a temporary vault directory."""
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


@pytest.fixture
def app_config(vault_path: Path) -> AppConfig:
    """Create an AppConfig pointing to a temporary vault."""
    return AppConfig(vault_path=vault_path)


@pytest.fixture
def db_engine(app_config: AppConfig) -> Engine:
    """Create a temporary database engine with all tables registered.

    Imports the models module to ensure SQLModel table definitions are
    registered before ``create_all`` is called.
    """
    import obsidian_note_linker.infrastructure.models  # noqa: F401
    from obsidian_note_linker.infrastructure.database import create_db_engine

    return create_db_engine(db_path=app_config.db_path)


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    """Reset logging handlers after each test to prevent leakage."""
    yield
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
