"""SQLite database setup and engine management."""

import logging
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine

logger = logging.getLogger(__name__)


def create_db_engine(db_path: Path) -> Engine:
    """Create a SQLite engine with WAL mode enabled.

    Creates the parent directory if it doesn't exist. Initialises all
    SQLModel tables defined in the metadata and runs any pending
    schema migrations.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A configured SQLAlchemy Engine.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_wal_mode(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[union-attr]
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    SQLModel.metadata.create_all(engine)
    _run_migrations(engine)
    logger.info("Database engine created at %s", db_path)
    return engine


def _run_migrations(engine: Engine) -> None:
    """Apply schema migrations for columns added after initial release.

    Uses idempotent ``ALTER TABLE ADD COLUMN`` guarded by column
    existence checks, so it is safe to call on every startup.

    Args:
        engine: SQLAlchemy engine for the database.
    """
    with engine.connect() as conn:
        # Migration: add applied_at column to decisions table (Slice 5)
        result = conn.execute(text("PRAGMA table_info(decisions)"))
        columns = {row[1] for row in result}
        if "applied_at" in columns:
            return

        conn.execute(
            text("ALTER TABLE decisions ADD COLUMN applied_at TIMESTAMP")
        )
        conn.commit()
        logger.info("Migration: added 'applied_at' column to decisions table")
