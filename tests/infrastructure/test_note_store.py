"""Tests for NoteRecord CRUD operations."""

from sqlalchemy.engine import Engine

from obsidian_note_linker.infrastructure.note_store import (
    count_note_records,
    delete_note_records,
    get_all_note_records,
    get_note_record_by_path,
    upsert_note_record,
)


class TestGetAllNoteRecords:
    """Tests for retrieving all note records."""

    def test_empty_database_returns_empty_list(self, db_engine: Engine) -> None:
        assert get_all_note_records(db_engine) == []

    def test_returns_all_inserted_records(self, db_engine: Engine) -> None:
        upsert_note_record(db_engine, relative_path="a.md", content_hash="hash_a")
        upsert_note_record(db_engine, relative_path="b.md", content_hash="hash_b")

        records = get_all_note_records(db_engine)

        assert len(records) == 2


class TestGetNoteRecordByPath:
    """Tests for retrieving a note record by path."""

    def test_returns_none_when_not_found(self, db_engine: Engine) -> None:
        assert get_note_record_by_path(db_engine, relative_path="missing.md") is None

    def test_returns_matching_record(self, db_engine: Engine) -> None:
        upsert_note_record(db_engine, relative_path="note.md", content_hash="abc")

        record = get_note_record_by_path(db_engine, relative_path="note.md")

        assert record is not None
        assert record.content_hash == "abc"


class TestUpsertNoteRecord:
    """Tests for insert/update of note records."""

    def test_inserts_new_record(self, db_engine: Engine) -> None:
        record = upsert_note_record(
            db_engine, relative_path="new.md", content_hash="hash1",
        )

        assert record.id is not None, "Should have an auto-generated ID"
        assert record.relative_path == "new.md"
        assert record.content_hash == "hash1"

    def test_updates_existing_record(self, db_engine: Engine) -> None:
        upsert_note_record(db_engine, relative_path="note.md", content_hash="old_hash")
        updated = upsert_note_record(
            db_engine, relative_path="note.md", content_hash="new_hash",
        )

        assert updated.content_hash == "new_hash", "Should update content hash"
        assert count_note_records(db_engine) == 1, "Should not create duplicate"

    def test_update_refreshes_indexed_at(self, db_engine: Engine) -> None:
        original = upsert_note_record(
            db_engine, relative_path="note.md", content_hash="hash1",
        )
        original_time = original.indexed_at

        updated = upsert_note_record(
            db_engine, relative_path="note.md", content_hash="hash2",
        )

        assert updated.indexed_at >= original_time, "Should update timestamp"


class TestDeleteNoteRecords:
    """Tests for deleting note records."""

    def test_deletes_existing_records(self, db_engine: Engine) -> None:
        upsert_note_record(db_engine, relative_path="a.md", content_hash="ha")
        upsert_note_record(db_engine, relative_path="b.md", content_hash="hb")

        deleted = delete_note_records(db_engine, relative_paths=["a.md"])

        assert deleted == 1
        assert count_note_records(db_engine) == 1

    def test_returns_zero_for_missing_paths(self, db_engine: Engine) -> None:
        deleted = delete_note_records(db_engine, relative_paths=["nonexistent.md"])

        assert deleted == 0

    def test_empty_list_deletes_nothing(self, db_engine: Engine) -> None:
        upsert_note_record(db_engine, relative_path="note.md", content_hash="h")

        deleted = delete_note_records(db_engine, relative_paths=[])

        assert deleted == 0
        assert count_note_records(db_engine) == 1


class TestCountNoteRecords:
    """Tests for counting note records."""

    def test_zero_when_empty(self, db_engine: Engine) -> None:
        assert count_note_records(db_engine) == 0

    def test_counts_all_records(self, db_engine: Engine) -> None:
        upsert_note_record(db_engine, relative_path="a.md", content_hash="ha")
        upsert_note_record(db_engine, relative_path="b.md", content_hash="hb")

        assert count_note_records(db_engine) == 2
