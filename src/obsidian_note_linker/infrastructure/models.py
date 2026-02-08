"""SQLModel table definitions for vault state persistence.

Tables:
    NoteRecord: Tracks indexed notes and their content hashes.
    EmbeddingRecord: Caches embedding vectors keyed by content hash.
    DecisionRecord: Persists human review decisions (YES/NO) for note pairs.
    AuditRecord: Logs all file modifications made by the application.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, LargeBinary, UniqueConstraint
from sqlmodel import Field, SQLModel


class NoteRecord(SQLModel, table=True):
    """Persistent record of an indexed note in the vault.

    Used to detect which notes are new, changed, or deleted between runs.
    """

    __tablename__ = "notes"

    id: int | None = Field(default=None, primary_key=True)
    relative_path: str = Field(index=True, unique=True)
    content_hash: str
    indexed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class EmbeddingRecord(SQLModel, table=True):
    """Cached embedding vector keyed by content hash.

    Embeddings are stored as binary blobs (arrays of single-precision floats).
    Keyed by content hash so identical content reuses the same embedding,
    even across different file paths.
    """

    __tablename__ = "embeddings"

    id: int | None = Field(default=None, primary_key=True)
    content_hash: str = Field(index=True, unique=True)
    embedding: bytes = Field(sa_column=Column("embedding", LargeBinary, nullable=False))
    model_name: str
    dimension: int
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class DecisionRecord(SQLModel, table=True):
    """Persisted human review decision for a candidate note pair.

    Stores YES or NO decisions with the content hashes at the time of
    the decision.  When either note is modified (hash changes), the
    decision is considered invalid and the pair reappears for review.

    Paths are stored in sorted order (note_a_path < note_b_path) to
    ensure canonical pair representation.
    """

    __tablename__ = "decisions"
    __table_args__ = (
        UniqueConstraint("note_a_path", "note_b_path", name="uq_decision_pair"),
    )

    id: int | None = Field(default=None, primary_key=True)
    note_a_path: str = Field(index=True)
    note_b_path: str = Field(index=True)
    decision: str  # "YES" or "NO"
    note_a_hash: str
    note_b_hash: str
    decided_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    applied_at: datetime | None = Field(default=None)


class AuditRecord(SQLModel, table=True):
    """Log entry for a file modification made by the application.

    Every write to a note file is recorded here for auditability (FR3.6).
    """

    __tablename__ = "audit_log"

    id: int | None = Field(default=None, primary_key=True)
    note_path: str = Field(index=True)
    action: str  # e.g. "ADD_LINK"
    detail: str  # Human-readable description of the change
    content_hash_before: str
    content_hash_after: str
    performed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
