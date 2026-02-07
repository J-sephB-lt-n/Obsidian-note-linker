"""Tests for vault scanning."""

from pathlib import Path

import pytest

from obsidian_note_linker.domain.note import compute_content_hash
from obsidian_note_linker.infrastructure.vault_scanner import scan_vault


class TestScanVault:
    """Tests for reading markdown files from a vault."""

    def test_finds_markdown_files(self, vault_path: Path) -> None:
        (vault_path / "note1.md").write_text("Hello", encoding="utf-8")
        (vault_path / "note2.md").write_text("World", encoding="utf-8")

        notes = scan_vault(vault_path)

        assert len(notes) == 2, "Should find both markdown files"

    def test_returns_relative_paths(self, vault_path: Path) -> None:
        (vault_path / "note.md").write_text("Content", encoding="utf-8")

        notes = scan_vault(vault_path)

        assert notes[0].relative_path == Path("note.md"), "Path should be relative to vault"

    def test_reads_content(self, vault_path: Path) -> None:
        (vault_path / "note.md").write_text("# My Note\n\nHello!", encoding="utf-8")

        notes = scan_vault(vault_path)

        assert notes[0].content == "# My Note\n\nHello!"

    def test_computes_content_hash(self, vault_path: Path) -> None:
        content = "Test content"
        (vault_path / "note.md").write_text(content, encoding="utf-8")

        notes = scan_vault(vault_path)

        assert notes[0].content_hash == compute_content_hash(content)

    def test_finds_nested_files(self, vault_path: Path) -> None:
        subdir = vault_path / "subfolder"
        subdir.mkdir()
        (subdir / "nested.md").write_text("Nested", encoding="utf-8")

        notes = scan_vault(vault_path)

        assert len(notes) == 1
        assert notes[0].relative_path == Path("subfolder/nested.md")

    def test_excludes_obsidian_directory(self, vault_path: Path) -> None:
        obsidian = vault_path / ".obsidian"
        obsidian.mkdir()
        (obsidian / "config.md").write_text("Config", encoding="utf-8")
        (vault_path / "note.md").write_text("Note", encoding="utf-8")

        notes = scan_vault(vault_path)

        assert len(notes) == 1, "Should exclude .obsidian/ directory"
        assert notes[0].relative_path == Path("note.md")

    def test_excludes_obsidian_linker_directory(self, vault_path: Path) -> None:
        state_dir = vault_path / ".obsidian-linker"
        state_dir.mkdir()
        (state_dir / "something.md").write_text("State", encoding="utf-8")
        (vault_path / "note.md").write_text("Note", encoding="utf-8")

        notes = scan_vault(vault_path)

        assert len(notes) == 1, "Should exclude .obsidian-linker/ directory"

    def test_ignores_non_markdown_files(self, vault_path: Path) -> None:
        (vault_path / "note.md").write_text("Markdown", encoding="utf-8")
        (vault_path / "image.png").write_bytes(b"\x89PNG")
        (vault_path / "data.json").write_text("{}", encoding="utf-8")

        notes = scan_vault(vault_path)

        assert len(notes) == 1, "Should only find .md files"

    def test_empty_vault_returns_empty_list(self, vault_path: Path) -> None:
        assert scan_vault(vault_path) == []

    def test_raises_for_nonexistent_path(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            scan_vault(tmp_path / "nonexistent")

    def test_returns_sorted_by_path(self, vault_path: Path) -> None:
        (vault_path / "zebra.md").write_text("Z", encoding="utf-8")
        (vault_path / "alpha.md").write_text("A", encoding="utf-8")
        (vault_path / "middle.md").write_text("M", encoding="utf-8")

        notes = scan_vault(vault_path)
        paths = [n.relative_path.name for n in notes]

        assert paths == ["alpha.md", "middle.md", "zebra.md"], "Should be sorted"
