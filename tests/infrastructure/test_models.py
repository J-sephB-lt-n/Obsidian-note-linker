"""Tests for SQLModel table definitions."""

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from obsidian_note_linker.infrastructure.models import EmbeddingRecord, NoteRecord


class TestNoteRecordTable:
    """Tests for the NoteRecord table."""

    def test_insert_and_retrieve(self, db_engine: Engine) -> None:
        with Session(db_engine) as session:
            record = NoteRecord(relative_path="notes/test.md", content_hash="abc123")
            session.add(record)
            session.commit()
            session.refresh(record)

        with Session(db_engine) as session:
            result = session.exec(select(NoteRecord)).first()

        assert result is not None, "Should retrieve inserted record"
        assert result.relative_path == "notes/test.md"
        assert result.content_hash == "abc123"
        assert result.indexed_at is not None, "Should have default indexed_at"

    def test_relative_path_is_unique(self, db_engine: Engine) -> None:
        with Session(db_engine) as session:
            session.add(NoteRecord(relative_path="a.md", content_hash="hash1"))
            session.commit()

        with Session(db_engine) as session:
            session.add(NoteRecord(relative_path="a.md", content_hash="hash2"))
            try:
                session.commit()
                raise AssertionError("Should have raised IntegrityError")  # noqa: TRY301
            except IntegrityError:
                pass  # Expected


class TestEmbeddingRecordTable:
    """Tests for the EmbeddingRecord table."""

    def test_insert_and_retrieve(self, db_engine: Engine) -> None:
        blob = b"\x00" * 12  # 3 floats × 4 bytes

        with Session(db_engine) as session:
            record = EmbeddingRecord(
                content_hash="abc123",
                embedding=blob,
                model_name="test-model",
                dimension=3,
            )
            session.add(record)
            session.commit()

        with Session(db_engine) as session:
            result = session.exec(select(EmbeddingRecord)).first()

        assert result is not None, "Should retrieve inserted record"
        assert result.content_hash == "abc123"
        assert result.embedding == blob
        assert result.model_name == "test-model"
        assert result.dimension == 3

    def test_content_hash_is_unique(self, db_engine: Engine) -> None:
        blob = b"\x00" * 4

        with Session(db_engine) as session:
            session.add(
                EmbeddingRecord(
                    content_hash="same", embedding=blob,
                    model_name="m", dimension=1,
                )
            )
            session.commit()

        with Session(db_engine) as session:
            session.add(
                EmbeddingRecord(
                    content_hash="same", embedding=blob,
                    model_name="m", dimension=1,
                )
            )
            try:
                session.commit()
                raise AssertionError("Should have raised IntegrityError")  # noqa: TRY301
            except IntegrityError:
                pass  # Expected
