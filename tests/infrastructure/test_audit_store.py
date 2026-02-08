"""Tests for audit store CRUD operations."""

from obsidian_note_linker.infrastructure.audit_store import (
    get_audit_log,
    save_audit_entry,
)


class TestSaveAuditEntry:
    """Tests for saving audit log entries."""

    def test_saves_audit_entry(self, db_engine) -> None:
        record = save_audit_entry(
            engine=db_engine,
            note_path="a.md",
            action="ADD_LINK",
            detail="Added link to b.md",
            content_hash_before="hash_before",
            content_hash_after="hash_after",
        )
        assert record.id is not None
        assert record.note_path == "a.md"
        assert record.action == "ADD_LINK"

    def test_audit_entry_has_timestamp(self, db_engine) -> None:
        record = save_audit_entry(
            engine=db_engine,
            note_path="a.md",
            action="ADD_LINK",
            detail="Added link",
            content_hash_before="h1",
            content_hash_after="h2",
        )
        assert record.performed_at is not None

    def test_multiple_entries_for_same_note(self, db_engine) -> None:
        save_audit_entry(
            engine=db_engine,
            note_path="a.md",
            action="ADD_LINK",
            detail="Added link to b.md",
            content_hash_before="h1",
            content_hash_after="h2",
        )
        save_audit_entry(
            engine=db_engine,
            note_path="a.md",
            action="ADD_LINK",
            detail="Added link to c.md",
            content_hash_before="h2",
            content_hash_after="h3",
        )
        entries = get_audit_log(engine=db_engine, note_path="a.md")
        assert len(entries) == 2


class TestGetAuditLog:
    """Tests for retrieving audit log entries."""

    def test_returns_entries_for_note(self, db_engine) -> None:
        save_audit_entry(
            engine=db_engine,
            note_path="a.md",
            action="ADD_LINK",
            detail="link added",
            content_hash_before="h1",
            content_hash_after="h2",
        )
        entries = get_audit_log(engine=db_engine, note_path="a.md")
        assert len(entries) == 1
        assert entries[0].note_path == "a.md"

    def test_returns_empty_for_unknown_note(self, db_engine) -> None:
        entries = get_audit_log(engine=db_engine, note_path="unknown.md")
        assert entries == []

    def test_filters_by_note_path(self, db_engine) -> None:
        save_audit_entry(
            engine=db_engine,
            note_path="a.md",
            action="ADD_LINK",
            detail="link to b",
            content_hash_before="h1",
            content_hash_after="h2",
        )
        save_audit_entry(
            engine=db_engine,
            note_path="b.md",
            action="ADD_LINK",
            detail="link to a",
            content_hash_before="h3",
            content_hash_after="h4",
        )
        entries = get_audit_log(engine=db_engine, note_path="a.md")
        assert len(entries) == 1
        assert entries[0].note_path == "a.md"

    def test_returns_all_entries_without_filter(self, db_engine) -> None:
        save_audit_entry(
            engine=db_engine,
            note_path="a.md",
            action="ADD_LINK",
            detail="link",
            content_hash_before="h1",
            content_hash_after="h2",
        )
        save_audit_entry(
            engine=db_engine,
            note_path="b.md",
            action="ADD_LINK",
            detail="link",
            content_hash_before="h3",
            content_hash_after="h4",
        )
        entries = get_audit_log(engine=db_engine)
        assert len(entries) == 2

    def test_ordered_by_most_recent_first(self, db_engine) -> None:
        save_audit_entry(
            engine=db_engine,
            note_path="a.md",
            action="ADD_LINK",
            detail="first",
            content_hash_before="h1",
            content_hash_after="h2",
        )
        save_audit_entry(
            engine=db_engine,
            note_path="a.md",
            action="ADD_LINK",
            detail="second",
            content_hash_before="h2",
            content_hash_after="h3",
        )
        entries = get_audit_log(engine=db_engine, note_path="a.md")
        assert entries[0].detail == "second"
        assert entries[1].detail == "first"
