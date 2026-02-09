"""Tests for the link integrity service."""

from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from obsidian_note_linker.domain.related_section_parser import IncompleteLink
from obsidian_note_linker.infrastructure.audit_store import get_audit_log
from obsidian_note_linker.services.integrity_service import (
    IntegrityService,
    ResolutionPreview,
    detect_incomplete_links,
)


def _create_note(vault_path: Path, rel_path: str, content: str) -> None:
    """Create a note file on disk."""
    full_path = vault_path / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")


class TestDetectIncompleteLinks:
    """Tests for the standalone detection function."""

    def test_detects_incomplete_link(self, vault_path: Path) -> None:
        _create_note(vault_path, "a.md", "## Related\n\n- [B](<b.md>)\n")
        _create_note(vault_path, "b.md", "# B\n\nContent.\n")

        result = detect_incomplete_links(vault_path)
        assert result == [
            IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md")),
        ]

    def test_returns_empty_for_bidirectional(self, vault_path: Path) -> None:
        _create_note(vault_path, "a.md", "## Related\n\n- [B](<b.md>)\n")
        _create_note(vault_path, "b.md", "## Related\n\n- [A](<a.md>)\n")

        result = detect_incomplete_links(vault_path)
        assert result == []

    def test_returns_empty_for_no_notes(self, vault_path: Path) -> None:
        result = detect_incomplete_links(vault_path)
        assert result == []

    def test_excludes_links_to_nonexistent_notes(self, vault_path: Path) -> None:
        _create_note(vault_path, "a.md", "## Related\n\n- [Ghost](<ghost.md>)\n")

        result = detect_incomplete_links(vault_path)
        assert result == []


class TestPreviewComplete:
    """Tests for IntegrityService.preview_complete()."""

    def test_returns_diff_for_target_note(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        _create_note(vault_path, "a.md", "## Related\n\n- [B](<b.md>)\n")
        _create_note(vault_path, "b.md", "# B\n\nContent.\n")

        service = IntegrityService(engine=db_engine, vault_path=vault_path)
        preview = service.preview_complete(
            source_path=Path("a.md"), target_path=Path("b.md"),
        )

        assert isinstance(preview, ResolutionPreview)
        assert preview.action == "complete"
        assert preview.modified_note_path == Path("b.md")
        assert "a.md" in preview.diff
        assert "## Related" in preview.diff

    def test_preview_includes_titles(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        _create_note(vault_path, "alpha.md", "## Related\n\n- [Beta](<beta.md>)\n")
        _create_note(vault_path, "beta.md", "# Beta\n")

        service = IntegrityService(engine=db_engine, vault_path=vault_path)
        preview = service.preview_complete(
            source_path=Path("alpha.md"), target_path=Path("beta.md"),
        )

        assert preview.source_title == "alpha"
        assert preview.target_title == "beta"

    def test_raises_for_missing_file(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        service = IntegrityService(engine=db_engine, vault_path=vault_path)
        with pytest.raises(FileNotFoundError):
            service.preview_complete(
                source_path=Path("missing.md"), target_path=Path("also_missing.md"),
            )


class TestPreviewRemove:
    """Tests for IntegrityService.preview_remove()."""

    def test_returns_diff_for_source_note(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        _create_note(
            vault_path, "a.md",
            "# A\n\n## Related\n\n- [B](<b.md>)\n",
        )
        _create_note(vault_path, "b.md", "# B\n\nContent.\n")

        service = IntegrityService(engine=db_engine, vault_path=vault_path)
        preview = service.preview_remove(
            source_path=Path("a.md"), target_path=Path("b.md"),
        )

        assert isinstance(preview, ResolutionPreview)
        assert preview.action == "remove"
        assert preview.modified_note_path == Path("a.md")
        assert "b.md" in preview.diff

    def test_diff_shows_removal_of_link(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        _create_note(
            vault_path, "a.md",
            "# A\n\n## Related\n\n- [B](<b.md>)\n- [C](<c.md>)\n",
        )
        _create_note(vault_path, "b.md", "# B\n")

        service = IntegrityService(engine=db_engine, vault_path=vault_path)
        preview = service.preview_remove(
            source_path=Path("a.md"), target_path=Path("b.md"),
        )

        # Diff should show removal of the B link but C link stays
        assert "-" in preview.diff and "b.md" in preview.diff


class TestApplyComplete:
    """Tests for IntegrityService.apply_complete()."""

    def test_adds_link_to_target_note(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        _create_note(vault_path, "a.md", "## Related\n\n- [B](<b.md>)\n")
        _create_note(vault_path, "b.md", "# B\n\nContent.\n")

        service = IntegrityService(engine=db_engine, vault_path=vault_path)
        service.apply_complete(
            source_path=Path("a.md"), target_path=Path("b.md"),
        )

        content_b = (vault_path / "b.md").read_text(encoding="utf-8")
        assert "a.md" in content_b
        assert "## Related" in content_b

    def test_does_not_modify_source_note(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        source_content = "## Related\n\n- [B](<b.md>)\n"
        _create_note(vault_path, "a.md", source_content)
        _create_note(vault_path, "b.md", "# B\n")

        service = IntegrityService(engine=db_engine, vault_path=vault_path)
        service.apply_complete(
            source_path=Path("a.md"), target_path=Path("b.md"),
        )

        content_a = (vault_path / "a.md").read_text(encoding="utf-8")
        assert content_a == source_content

    def test_creates_audit_entry(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        _create_note(vault_path, "a.md", "## Related\n\n- [B](<b.md>)\n")
        _create_note(vault_path, "b.md", "# B\n")

        service = IntegrityService(engine=db_engine, vault_path=vault_path)
        service.apply_complete(
            source_path=Path("a.md"), target_path=Path("b.md"),
        )

        audit = get_audit_log(engine=db_engine, note_path="b.md")
        assert len(audit) == 1
        assert audit[0].action == "COMPLETE_LINK"

    def test_handles_spaces_in_paths(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        _create_note(
            vault_path, "My Note.md",
            "## Related\n\n- [Other Note](<Other%20Note.md>)\n",
        )
        _create_note(vault_path, "Other Note.md", "# Other\n")

        service = IntegrityService(engine=db_engine, vault_path=vault_path)
        service.apply_complete(
            source_path=Path("My Note.md"), target_path=Path("Other Note.md"),
        )

        content = (vault_path / "Other Note.md").read_text(encoding="utf-8")
        assert "My%20Note.md" in content


class TestApplyRemove:
    """Tests for IntegrityService.apply_remove()."""

    def test_removes_link_from_source_note(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        _create_note(
            vault_path, "a.md",
            "# A\n\n## Related\n\n- [B](<b.md>)\n- [C](<c.md>)\n",
        )
        _create_note(vault_path, "b.md", "# B\n")

        service = IntegrityService(engine=db_engine, vault_path=vault_path)
        service.apply_remove(
            source_path=Path("a.md"), target_path=Path("b.md"),
        )

        content_a = (vault_path / "a.md").read_text(encoding="utf-8")
        assert "b.md" not in content_a
        assert "c.md" in content_a

    def test_does_not_modify_target_note(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        target_content = "# B\n\nContent.\n"
        _create_note(vault_path, "a.md", "## Related\n\n- [B](<b.md>)\n")
        _create_note(vault_path, "b.md", target_content)

        service = IntegrityService(engine=db_engine, vault_path=vault_path)
        service.apply_remove(
            source_path=Path("a.md"), target_path=Path("b.md"),
        )

        content_b = (vault_path / "b.md").read_text(encoding="utf-8")
        assert content_b == target_content

    def test_creates_audit_entry(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        _create_note(vault_path, "a.md", "## Related\n\n- [B](<b.md>)\n")
        _create_note(vault_path, "b.md", "# B\n")

        service = IntegrityService(engine=db_engine, vault_path=vault_path)
        service.apply_remove(
            source_path=Path("a.md"), target_path=Path("b.md"),
        )

        audit = get_audit_log(engine=db_engine, note_path="a.md")
        assert len(audit) == 1
        assert audit[0].action == "REMOVE_LINK"

    def test_removes_section_when_last_link_removed(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        _create_note(
            vault_path, "a.md",
            "# A\n\nContent.\n\n## Related\n\n- [B](<b.md>)\n",
        )
        _create_note(vault_path, "b.md", "# B\n")

        service = IntegrityService(engine=db_engine, vault_path=vault_path)
        service.apply_remove(
            source_path=Path("a.md"), target_path=Path("b.md"),
        )

        content_a = (vault_path / "a.md").read_text(encoding="utf-8")
        assert "## Related" not in content_a

    def test_raises_for_missing_file(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        service = IntegrityService(engine=db_engine, vault_path=vault_path)
        with pytest.raises(FileNotFoundError):
            service.apply_remove(
                source_path=Path("missing.md"), target_path=Path("b.md"),
            )
