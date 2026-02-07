"""Tests for SQLModel table definitions."""

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from obsidian_note_linker.infrastructure.models import (
    DecisionRecord,
    EmbeddingRecord,
    NoteRecord,
)


class TestNoteRecordTable:
    """Tests for the NoteRecord table."""

    def test_insert_and_retrieve(self, db_engine):
        record = NoteRecord(relative_path="test.md", content_hash="abc123")
        with Session(db_engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)

        assert record.id is not None
        assert record.relative_path == "test.md"
        assert record.content_hash == "abc123"
        assert isinstance(record.indexed_at, datetime)

    def test_relative_path_is_unique(self, db_engine):
        with Session(db_engine) as session:
            session.add(NoteRecord(relative_path="dup.md", content_hash="aaa"))
            session.commit()

        with pytest.raises(IntegrityError):
            with Session(db_engine) as session:
                session.add(NoteRecord(relative_path="dup.md", content_hash="bbb"))
                session.commit()


class TestEmbeddingRecordTable:
    """Tests for the EmbeddingRecord table."""

    def test_insert_and_retrieve(self, db_engine):
        record = EmbeddingRecord(
            content_hash="hash1",
            embedding=b"\x00\x01\x02\x03",
            model_name="test-model",
            dimension=128,
        )
        with Session(db_engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)

        assert record.id is not None
        assert record.content_hash == "hash1"

    def test_content_hash_is_unique(self, db_engine):
        with Session(db_engine) as session:
            session.add(
                EmbeddingRecord(
                    content_hash="same",
                    embedding=b"\x00",
                    model_name="m",
                    dimension=1,
                )
            )
            session.commit()

        with pytest.raises(IntegrityError):
            with Session(db_engine) as session:
                session.add(
                    EmbeddingRecord(
                        content_hash="same",
                        embedding=b"\x01",
                        model_name="m",
                        dimension=1,
                    )
                )
                session.commit()


class TestDecisionRecordTable:
    """Tests for the DecisionRecord table."""

    def test_insert_and_retrieve(self, db_engine):
        record = DecisionRecord(
            note_a_path="a.md",
            note_b_path="b.md",
            decision="YES",
            note_a_hash="hash_a",
            note_b_hash="hash_b",
        )
        with Session(db_engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)

        assert record.id is not None
        assert record.note_a_path == "a.md"
        assert record.note_b_path == "b.md"
        assert record.decision == "YES"
        assert record.note_a_hash == "hash_a"
        assert record.note_b_hash == "hash_b"
        assert isinstance(record.decided_at, datetime)

    def test_note_pair_is_unique(self, db_engine):
        """Only one decision per (note_a_path, note_b_path) pair."""
        with Session(db_engine) as session:
            session.add(
                DecisionRecord(
                    note_a_path="a.md",
                    note_b_path="b.md",
                    decision="YES",
                    note_a_hash="h1",
                    note_b_hash="h2",
                )
            )
            session.commit()

        with pytest.raises(IntegrityError):
            with Session(db_engine) as session:
                session.add(
                    DecisionRecord(
                        note_a_path="a.md",
                        note_b_path="b.md",
                        decision="NO",
                        note_a_hash="h3",
                        note_b_hash="h4",
                    )
                )
                session.commit()

    def test_stores_both_yes_and_no(self, db_engine):
        with Session(db_engine) as session:
            session.add(
                DecisionRecord(
                    note_a_path="a.md",
                    note_b_path="b.md",
                    decision="YES",
                    note_a_hash="h1",
                    note_b_hash="h2",
                )
            )
            session.add(
                DecisionRecord(
                    note_a_path="c.md",
                    note_b_path="d.md",
                    decision="NO",
                    note_a_hash="h3",
                    note_b_hash="h4",
                )
            )
            session.commit()
