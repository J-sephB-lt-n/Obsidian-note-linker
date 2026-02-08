"""Tests for the link application service."""

from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from obsidian_note_linker.domain.note import compute_content_hash
from obsidian_note_linker.infrastructure.audit_store import get_audit_log
from obsidian_note_linker.infrastructure.decision_store import (
    get_pending_approved_pairs,
    save_decision,
)
from obsidian_note_linker.infrastructure.note_store import upsert_note_record
from obsidian_note_linker.services.link_service import LinkService, PairDiffPreview


def _setup_vault_notes(
    vault_path: Path,
    db_engine: Engine,
    notes: dict[str, str],
) -> None:
    """Create note files on disk and upsert note records in DB."""
    for rel_path, content in notes.items():
        full_path = vault_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        upsert_note_record(
            engine=db_engine,
            relative_path=rel_path,
            content_hash=compute_content_hash(content),
        )


def _approve_pair(
    db_engine: Engine,
    notes: dict[str, str],
    note_a: str,
    note_b: str,
) -> None:
    """Save a YES decision for a pair."""
    save_decision(
        engine=db_engine,
        note_a_path=note_a,
        note_b_path=note_b,
        decision="YES",
        note_a_hash=compute_content_hash(notes[note_a]),
        note_b_hash=compute_content_hash(notes[note_b]),
    )


class TestGetPendingPairs:
    """Tests for LinkService.get_pending_pairs()."""

    def test_returns_pending_approved_pairs(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        notes = {"a.md": "# A\n\nContent A", "b.md": "# B\n\nContent B"}
        _setup_vault_notes(vault_path, db_engine, notes)
        _approve_pair(db_engine, notes, "a.md", "b.md")

        service = LinkService(engine=db_engine, vault_path=vault_path)
        pairs = service.get_pending_pairs()
        assert len(pairs) == 1

    def test_returns_empty_when_no_approvals(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        service = LinkService(engine=db_engine, vault_path=vault_path)
        pairs = service.get_pending_pairs()
        assert pairs == []


class TestPreviewPair:
    """Tests for LinkService.preview_pair()."""

    def test_returns_diffs_for_both_notes(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        notes = {"a.md": "# A\n\nContent A\n", "b.md": "# B\n\nContent B\n"}
        _setup_vault_notes(vault_path, db_engine, notes)
        _approve_pair(db_engine, notes, "a.md", "b.md")

        service = LinkService(engine=db_engine, vault_path=vault_path)
        pairs = service.get_pending_pairs()
        preview = service.preview_pair(pairs[0])

        assert isinstance(preview, PairDiffPreview)
        assert preview.note_a_path == Path("a.md")
        assert preview.note_b_path == Path("b.md")
        assert "## Related" in preview.note_a_diff
        assert "## Related" in preview.note_b_diff

    def test_diff_shows_link_to_other_note(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        notes = {"a.md": "# A\n\nContent A\n", "b.md": "# B\n\nContent B\n"}
        _setup_vault_notes(vault_path, db_engine, notes)
        _approve_pair(db_engine, notes, "a.md", "b.md")

        service = LinkService(engine=db_engine, vault_path=vault_path)
        pairs = service.get_pending_pairs()
        preview = service.preview_pair(pairs[0])

        # Note A's diff should contain a link to B
        assert "b.md" in preview.note_a_diff
        # Note B's diff should contain a link to A
        assert "a.md" in preview.note_b_diff

    def test_diff_empty_when_link_already_exists(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        """If both notes already link to each other, diffs should be empty."""
        notes = {
            "a.md": "# A\n\n## Related\n\n- [b](<b.md>)\n",
            "b.md": "# B\n\n## Related\n\n- [a](<a.md>)\n",
        }
        _setup_vault_notes(vault_path, db_engine, notes)
        _approve_pair(db_engine, notes, "a.md", "b.md")

        service = LinkService(engine=db_engine, vault_path=vault_path)
        pairs = service.get_pending_pairs()
        preview = service.preview_pair(pairs[0])

        assert preview.note_a_diff == ""
        assert preview.note_b_diff == ""

    def test_preview_includes_note_titles(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        notes = {"alpha.md": "# Alpha\n", "beta.md": "# Beta\n"}
        _setup_vault_notes(vault_path, db_engine, notes)
        _approve_pair(db_engine, notes, "alpha.md", "beta.md")

        service = LinkService(engine=db_engine, vault_path=vault_path)
        pairs = service.get_pending_pairs()
        preview = service.preview_pair(pairs[0])

        assert preview.note_a_title == "alpha"
        assert preview.note_b_title == "beta"


class TestApplyPair:
    """Tests for LinkService.apply_pair()."""

    def test_writes_links_to_both_files(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        notes = {"a.md": "# A\n\nContent A\n", "b.md": "# B\n\nContent B\n"}
        _setup_vault_notes(vault_path, db_engine, notes)
        _approve_pair(db_engine, notes, "a.md", "b.md")

        service = LinkService(engine=db_engine, vault_path=vault_path)
        pairs = service.get_pending_pairs()
        service.apply_pair(pairs[0])

        content_a = (vault_path / "a.md").read_text(encoding="utf-8")
        content_b = (vault_path / "b.md").read_text(encoding="utf-8")
        assert "b.md" in content_a
        assert "a.md" in content_b

    def test_creates_related_section(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        notes = {"a.md": "# A\n\nContent.\n", "b.md": "# B\n\nContent.\n"}
        _setup_vault_notes(vault_path, db_engine, notes)
        _approve_pair(db_engine, notes, "a.md", "b.md")

        service = LinkService(engine=db_engine, vault_path=vault_path)
        pairs = service.get_pending_pairs()
        service.apply_pair(pairs[0])

        content_a = (vault_path / "a.md").read_text(encoding="utf-8")
        assert "## Related" in content_a

    def test_marks_decision_as_applied(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        notes = {"a.md": "# A\n", "b.md": "# B\n"}
        _setup_vault_notes(vault_path, db_engine, notes)
        _approve_pair(db_engine, notes, "a.md", "b.md")

        service = LinkService(engine=db_engine, vault_path=vault_path)
        pairs = service.get_pending_pairs()
        service.apply_pair(pairs[0])

        remaining = get_pending_approved_pairs(engine=db_engine)
        assert len(remaining) == 0

    def test_creates_audit_entries(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        notes = {"a.md": "# A\n", "b.md": "# B\n"}
        _setup_vault_notes(vault_path, db_engine, notes)
        _approve_pair(db_engine, notes, "a.md", "b.md")

        service = LinkService(engine=db_engine, vault_path=vault_path)
        pairs = service.get_pending_pairs()
        service.apply_pair(pairs[0])

        audit_a = get_audit_log(engine=db_engine, note_path="a.md")
        audit_b = get_audit_log(engine=db_engine, note_path="b.md")
        assert len(audit_a) == 1
        assert len(audit_b) == 1
        assert audit_a[0].action == "ADD_LINK"
        assert audit_b[0].action == "ADD_LINK"

    def test_does_not_duplicate_existing_links(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        """If a link already exists, it should not be added again."""
        notes = {
            "a.md": "# A\n\n## Related\n\n- [b](<b.md>)\n",
            "b.md": "# B\n",
        }
        _setup_vault_notes(vault_path, db_engine, notes)
        _approve_pair(db_engine, notes, "a.md", "b.md")

        service = LinkService(engine=db_engine, vault_path=vault_path)
        pairs = service.get_pending_pairs()
        service.apply_pair(pairs[0])

        # a.md should still have only one link to b.md
        content_a = (vault_path / "a.md").read_text(encoding="utf-8")
        assert content_a.count("b.md") == 1
        # b.md should have a new link to a.md
        content_b = (vault_path / "b.md").read_text(encoding="utf-8")
        assert "a.md" in content_b

    def test_skips_writing_note_with_no_changes(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        """If a note already has the link, no audit entry should be created."""
        notes = {
            "a.md": "# A\n\n## Related\n\n- [b](<b.md>)\n",
            "b.md": "# B\n\n## Related\n\n- [a](<a.md>)\n",
        }
        _setup_vault_notes(vault_path, db_engine, notes)
        _approve_pair(db_engine, notes, "a.md", "b.md")

        service = LinkService(engine=db_engine, vault_path=vault_path)
        pairs = service.get_pending_pairs()
        service.apply_pair(pairs[0])

        # No audit entries because nothing was changed
        audit_a = get_audit_log(engine=db_engine, note_path="a.md")
        audit_b = get_audit_log(engine=db_engine, note_path="b.md")
        assert len(audit_a) == 0
        assert len(audit_b) == 0

    def test_handles_notes_with_spaces_in_path(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        notes = {
            "My Note.md": "# My Note\n",
            "Other Note.md": "# Other Note\n",
        }
        _setup_vault_notes(vault_path, db_engine, notes)
        _approve_pair(db_engine, notes, "My Note.md", "Other Note.md")

        service = LinkService(engine=db_engine, vault_path=vault_path)
        pairs = service.get_pending_pairs()
        service.apply_pair(pairs[0])

        content_a = (vault_path / "My Note.md").read_text(encoding="utf-8")
        content_b = (vault_path / "Other Note.md").read_text(encoding="utf-8")
        assert "Other%20Note.md" in content_a
        assert "My%20Note.md" in content_b

    def test_apply_pair_raises_for_missing_file(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        """If a note file doesn't exist on disk, apply should raise."""
        notes = {"a.md": "# A\n", "b.md": "# B\n"}
        _setup_vault_notes(vault_path, db_engine, notes)
        _approve_pair(db_engine, notes, "a.md", "b.md")

        # Delete the file from disk but leave the DB record
        (vault_path / "a.md").unlink()

        service = LinkService(engine=db_engine, vault_path=vault_path)
        pairs = service.get_pending_pairs()
        with pytest.raises(FileNotFoundError):
            service.apply_pair(pairs[0])
