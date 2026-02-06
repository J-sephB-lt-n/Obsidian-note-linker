"""Tests for database setup."""

from pathlib import Path

from sqlalchemy import text

from obsidian_note_linker.infrastructure.database import create_db_engine


class TestCreateDbEngine:
    """Tests for create_db_engine."""

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        db_path = tmp_path / "subdir" / "state.db"

        create_db_engine(db_path=db_path)

        assert db_path.parent.exists()

    def test_creates_database_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "state.db"

        create_db_engine(db_path=db_path)

        assert db_path.exists()

    def test_returns_working_engine(self, tmp_path: Path) -> None:
        db_path = tmp_path / "state.db"
        engine = create_db_engine(db_path=db_path)

        with engine.connect() as conn:
            (value,) = conn.execute(text("SELECT 1")).one()
            assert value == 1

    def test_enables_wal_mode(self, tmp_path: Path) -> None:
        db_path = tmp_path / "state.db"
        engine = create_db_engine(db_path=db_path)

        with engine.connect() as conn:
            (mode,) = conn.execute(text("PRAGMA journal_mode")).one()
            assert mode == "wal"
