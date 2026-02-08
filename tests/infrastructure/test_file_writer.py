"""Tests for atomic file writer."""

from pathlib import Path

import pytest

from obsidian_note_linker.infrastructure.file_writer import atomic_write


class TestAtomicWrite:
    """Tests for the atomic file writer."""

    def test_writes_content_to_file(self, tmp_path: Path) -> None:
        target = tmp_path / "note.md"
        target.write_text("original", encoding="utf-8")
        atomic_write(path=target, content="updated")
        assert target.read_text(encoding="utf-8") == "updated"

    def test_creates_file_if_not_exists(self, tmp_path: Path) -> None:
        target = tmp_path / "new_note.md"
        atomic_write(path=target, content="new content")
        assert target.read_text(encoding="utf-8") == "new content"

    def test_preserves_original_on_failure(self, tmp_path: Path) -> None:
        """If the write path is a directory (simulating a rename failure),
        the original file should remain untouched."""
        target = tmp_path / "note.md"
        target.write_text("original", encoding="utf-8")

        # Create a scenario where the temp file write would fail
        # by making the parent directory read-only
        read_only_dir = tmp_path / "readonly"
        read_only_dir.mkdir()
        protected_file = read_only_dir / "note.md"
        protected_file.write_text("original", encoding="utf-8")
        read_only_dir.chmod(0o444)

        try:
            with pytest.raises(OSError):
                atomic_write(path=protected_file, content="should fail")
            # Original content should still be there
            read_only_dir.chmod(0o755)
            assert protected_file.read_text(encoding="utf-8") == "original"
        finally:
            read_only_dir.chmod(0o755)

    def test_no_temp_files_left_behind(self, tmp_path: Path) -> None:
        target = tmp_path / "note.md"
        atomic_write(path=target, content="content")
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name == "note.md"

    def test_writes_utf8_content(self, tmp_path: Path) -> None:
        target = tmp_path / "unicode.md"
        content = "# Ünïcödé\n\nCôntënt with émojis 🎉\n"
        atomic_write(path=target, content=content)
        assert target.read_text(encoding="utf-8") == content

    def test_handles_nested_path(self, tmp_path: Path) -> None:
        target = tmp_path / "sub" / "dir" / "note.md"
        target.parent.mkdir(parents=True)
        atomic_write(path=target, content="nested")
        assert target.read_text(encoding="utf-8") == "nested"
