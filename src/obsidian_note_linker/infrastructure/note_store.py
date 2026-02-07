"""CRUD operations for NoteRecord persistence."""

import logging
from datetime import datetime, timezone

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from obsidian_note_linker.infrastructure.models import NoteRecord

logger = logging.getLogger(__name__)


def get_all_note_records(engine: Engine) -> list[NoteRecord]:
    """Retrieve all note records from the database.

    Args:
        engine: SQLAlchemy engine.

    Returns:
        List of all stored NoteRecord instances.
    """
    with Session(engine) as session:
        return list(session.exec(select(NoteRecord)).all())


def get_note_record_by_path(engine: Engine, relative_path: str) -> NoteRecord | None:
    """Retrieve a note record by its relative path.

    Args:
        engine: SQLAlchemy engine.
        relative_path: Relative path string to look up.

    Returns:
        The matching NoteRecord, or None if not found.
    """
    with Session(engine) as session:
        return session.exec(
            select(NoteRecord).where(NoteRecord.relative_path == relative_path)
        ).first()


def upsert_note_record(
    engine: Engine,
    relative_path: str,
    content_hash: str,
) -> NoteRecord:
    """Insert or update a note record.

    If a record with the given relative_path exists, updates its
    content_hash and indexed_at timestamp.  Otherwise inserts a new record.

    Args:
        engine: SQLAlchemy engine.
        relative_path: Relative path of the note within the vault.
        content_hash: SHA256 hex digest of the note content.

    Returns:
        The created or updated NoteRecord.
    """
    with Session(engine) as session:
        existing = session.exec(
            select(NoteRecord).where(NoteRecord.relative_path == relative_path)
        ).first()

        if existing:
            existing.content_hash = content_hash
            existing.indexed_at = datetime.now(timezone.utc)
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing

        record = NoteRecord(relative_path=relative_path, content_hash=content_hash)
        session.add(record)
        session.commit()
        session.refresh(record)
        logger.debug("Inserted note record: %s", relative_path)
        return record


def delete_note_records(engine: Engine, relative_paths: list[str]) -> int:
    """Delete note records by their relative paths.

    Args:
        engine: SQLAlchemy engine.
        relative_paths: List of relative path strings to delete.

    Returns:
        Number of records actually deleted.
    """
    deleted = 0
    with Session(engine) as session:
        for path in relative_paths:
            record = session.exec(
                select(NoteRecord).where(NoteRecord.relative_path == path)
            ).first()
            if record:
                session.delete(record)
                deleted += 1
        session.commit()

    if deleted:
        logger.info("Deleted %d note record(s)", deleted)
    return deleted


def count_note_records(engine: Engine) -> int:
    """Return the total number of indexed note records.

    Args:
        engine: SQLAlchemy engine.

    Returns:
        Count of note records in the database.
    """
    with Session(engine) as session:
        return len(list(session.exec(select(NoteRecord)).all()))
