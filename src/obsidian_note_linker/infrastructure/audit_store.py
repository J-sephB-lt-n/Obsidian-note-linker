"""CRUD operations for AuditRecord persistence.

Every file modification made by the application is logged here for
auditability (FR3.6, NFR1.2).
"""

import logging

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from obsidian_note_linker.infrastructure.models import AuditRecord

logger = logging.getLogger(__name__)


def save_audit_entry(
    engine: Engine,
    note_path: str,
    action: str,
    detail: str,
    content_hash_before: str,
    content_hash_after: str,
) -> AuditRecord:
    """Record a file modification in the audit log.

    Args:
        engine: SQLAlchemy engine.
        note_path: Relative path of the modified note.
        action: Type of modification (e.g. ``"ADD_LINK"``).
        detail: Human-readable description of the change.
        content_hash_before: SHA256 hash of note content before modification.
        content_hash_after: SHA256 hash of note content after modification.

    Returns:
        The created AuditRecord.
    """
    record = AuditRecord(
        note_path=note_path,
        action=action,
        detail=detail,
        content_hash_before=content_hash_before,
        content_hash_after=content_hash_after,
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)

    logger.info("Audit: %s on %s — %s", action, note_path, detail)
    return record


def get_audit_log(
    engine: Engine,
    note_path: str | None = None,
) -> list[AuditRecord]:
    """Retrieve audit log entries, optionally filtered by note path.

    Results are ordered by most recent first.

    Args:
        engine: SQLAlchemy engine.
        note_path: If provided, only return entries for this note.

    Returns:
        List of AuditRecord instances.
    """
    with Session(engine) as session:
        stmt = select(AuditRecord).order_by(AuditRecord.performed_at.desc())  # type: ignore[union-attr]
        if note_path is not None:
            stmt = stmt.where(AuditRecord.note_path == note_path)
        return list(session.exec(stmt).all())
