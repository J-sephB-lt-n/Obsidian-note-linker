"""SQLite database setup and engine management."""

import logging
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine

logger = logging.getLogger(__name__)


def create_db_engine(db_path: Path) -> Engine:
    """Create a SQLite engine with WAL mode enabled.

    Creates the parent directory if it doesn't exist. Initialises all
    SQLModel tables defined in the metadata.

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
    logger.info("Database engine created at %s", db_path)
    return engine
