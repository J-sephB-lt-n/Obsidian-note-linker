"""Tests for the link builder domain module."""

from pathlib import Path

from obsidian_note_linker.domain.link_builder import (
    compute_content_diff,
    format_obsidian_link,
    insert_links_into_content,
    remove_link_from_content,
)


class TestFormatObsidianLink:
    """Tests for formatting Obsidian markdown links."""

    def test_simple_note(self) -> None:
        result = format_obsidian_link(Path("Simple.md"))
        assert result == "- [Simple](<Simple.md>)"

    def test_note_with_spaces(self) -> None:
        result = format_obsidian_link(Path("My Cool Note.md"))
        assert result == "- [My Cool Note](<My%20Cool%20Note.md>)"

    def test_note_in_subdirectory(self) -> None:
        result = format_obsidian_link(Path("folder/Sub Note.md"))
        assert result == "- [Sub Note](<folder/Sub%20Note.md>)"

    def test_note_in_nested_subdirectory(self) -> None:
        result = format_obsidian_link(Path("a/b/Deep Note.md"))
        assert result == "- [Deep Note](<a/b/Deep%20Note.md>)"

    def test_note_with_special_characters(self) -> None:
        result = format_obsidian_link(Path("Note (Draft).md"))
        assert result == "- [Note (Draft)](<Note%20%28Draft%29.md>)"

    def test_note_without_spaces(self) -> None:
        result = format_obsidian_link(Path("note.md"))
        assert result == "- [note](<note.md>)"


class TestInsertLinksIntoContent:
    """Tests for inserting links into note content."""

    def test_creates_related_section_when_missing(self) -> None:
        content = "# My Note\n\nSome content.\n"
        links = ["- [Other](<Other.md>)"]
        result = insert_links_into_content(content=content, links=links)
        assert "## Related" in result
        assert "- [Other](<Other.md>)" in result

    def test_appends_to_existing_related_section(self) -> None:
        content = (
            "# My Note\n\nContent.\n\n"
            "## Related\n\n"
            "- [Existing](<Existing.md>)\n"
        )
        links = ["- [New](<New.md>)"]
        result = insert_links_into_content(content=content, links=links)
        assert "- [Existing](<Existing.md>)" in result
        assert "- [New](<New.md>)" in result

    def test_does_not_duplicate_existing_link(self) -> None:
        content = (
            "# My Note\n\n"
            "## Related\n\n"
            "- [Existing](<Existing.md>)\n"
        )
        links = ["- [Existing](<Existing.md>)"]
        result = insert_links_into_content(content=content, links=links)
        assert result.count("- [Existing](<Existing.md>)") == 1

    def test_inserts_multiple_links(self) -> None:
        content = "# My Note\n\nContent.\n"
        links = ["- [A](<A.md>)", "- [B](<B.md>)"]
        result = insert_links_into_content(content=content, links=links)
        assert "- [A](<A.md>)" in result
        assert "- [B](<B.md>)" in result

    def test_inserts_before_next_heading(self) -> None:
        content = (
            "# My Note\n\nContent.\n\n"
            "## Related\n\n"
            "- [Existing](<Existing.md>)\n\n"
            "## References\n\nSome references.\n"
        )
        links = ["- [New](<New.md>)"]
        result = insert_links_into_content(content=content, links=links)
        # New link should appear before ## References
        related_pos = result.index("## Related")
        new_link_pos = result.index("- [New](<New.md>)")
        references_pos = result.index("## References")
        assert related_pos < new_link_pos < references_pos

    def test_preserves_content_before_and_after(self) -> None:
        content = (
            "# My Note\n\nImportant content.\n\n"
            "## References\n\nSome refs.\n"
        )
        links = ["- [Other](<Other.md>)"]
        result = insert_links_into_content(content=content, links=links)
        assert "Important content." in result
        assert "## References" in result
        assert "Some refs." in result

    def test_empty_links_list_returns_unchanged(self) -> None:
        content = "# My Note\n\nContent.\n"
        result = insert_links_into_content(content=content, links=[])
        assert result == content

    def test_filters_duplicate_from_multiple_links(self) -> None:
        """When inserting multiple links, skip any that already exist."""
        content = (
            "## Related\n\n"
            "- [A](<A.md>)\n"
        )
        links = ["- [A](<A.md>)", "- [B](<B.md>)"]
        result = insert_links_into_content(content=content, links=links)
        assert result.count("- [A](<A.md>)") == 1
        assert "- [B](<B.md>)" in result

    def test_related_section_at_end_of_file(self) -> None:
        content = "# My Note\n\n## Related\n\n- [Old](<Old.md>)\n"
        links = ["- [New](<New.md>)"]
        result = insert_links_into_content(content=content, links=links)
        assert "- [Old](<Old.md>)" in result
        assert "- [New](<New.md>)" in result

    def test_new_related_section_placed_at_end(self) -> None:
        content = "# My Note\n\nContent here.\n"
        links = ["- [Other](<Other.md>)"]
        result = insert_links_into_content(content=content, links=links)
        # ## Related should be near the end
        assert result.endswith("- [Other](<Other.md>)\n")


class TestComputeContentDiff:
    """Tests for computing unified diffs between original and modified content."""

    def test_shows_added_lines(self) -> None:
        original = "# My Note\n\nContent.\n"
        modified = "# My Note\n\nContent.\n\n## Related\n\n- [Other](<Other.md>)\n"
        diff = compute_content_diff(
            original=original, modified=modified, filename="note.md",
        )
        assert "+## Related" in diff
        assert "+- [Other](<Other.md>)" in diff

    def test_shows_filename_in_header(self) -> None:
        original = "line 1\n"
        modified = "line 1\nline 2\n"
        diff = compute_content_diff(
            original=original, modified=modified, filename="test.md",
        )
        assert "test.md" in diff

    def test_empty_diff_when_no_changes(self) -> None:
        content = "# Same\n\nContent.\n"
        diff = compute_content_diff(
            original=content, modified=content, filename="same.md",
        )
        assert diff == ""

    def test_diff_preserves_context_lines(self) -> None:
        original = "line 1\nline 2\nline 3\n"
        modified = "line 1\nline 2\nline 3\nnew line\n"
        diff = compute_content_diff(
            original=original, modified=modified, filename="ctx.md",
        )
        # Context lines should be present
        assert "line 3" in diff


class TestRemoveLinkFromContent:
    """Tests for removing a specific link from the ## Related section."""

    def test_removes_target_link(self) -> None:
        content = (
            "# Note\n\nContent.\n\n"
            "## Related\n\n"
            "- [Alpha](<Alpha.md>)\n"
            "- [Beta](<Beta.md>)\n"
        )
        result = remove_link_from_content(
            content=content, target_path=Path("Alpha.md"),
        )
        assert "- [Alpha](<Alpha.md>)" not in result
        assert "- [Beta](<Beta.md>)" in result

    def test_removes_section_when_last_link_removed(self) -> None:
        """Removing the only link should also remove the ## Related heading."""
        content = (
            "# Note\n\nContent.\n\n"
            "## Related\n\n"
            "- [Only](<Only.md>)\n"
        )
        result = remove_link_from_content(
            content=content, target_path=Path("Only.md"),
        )
        assert "## Related" not in result
        assert "Content." in result

    def test_returns_unchanged_if_link_not_found(self) -> None:
        content = (
            "## Related\n\n"
            "- [A](<A.md>)\n"
        )
        result = remove_link_from_content(
            content=content, target_path=Path("B.md"),
        )
        assert result == content

    def test_returns_unchanged_if_no_related_section(self) -> None:
        content = "# Note\n\nJust content.\n"
        result = remove_link_from_content(
            content=content, target_path=Path("A.md"),
        )
        assert result == content

    def test_handles_percent_encoded_link(self) -> None:
        content = (
            "## Related\n\n"
            "- [My Note](<My%20Note.md>)\n"
            "- [Other](<Other.md>)\n"
        )
        result = remove_link_from_content(
            content=content, target_path=Path("My Note.md"),
        )
        assert "My Note" not in result
        assert "- [Other](<Other.md>)" in result

    def test_handles_subdirectory_target(self) -> None:
        content = (
            "## Related\n\n"
            "- [Sub](<sub/note.md>)\n"
            "- [Root](<root.md>)\n"
        )
        result = remove_link_from_content(
            content=content, target_path=Path("sub/note.md"),
        )
        assert "sub/note.md" not in result
        assert "- [Root](<root.md>)" in result

    def test_preserves_content_before_and_after_section(self) -> None:
        content = (
            "# Title\n\nParagraph.\n\n"
            "## Related\n\n"
            "- [A](<A.md>)\n"
            "- [B](<B.md>)\n\n"
            "## References\n\nRef content.\n"
        )
        result = remove_link_from_content(
            content=content, target_path=Path("A.md"),
        )
        assert "# Title" in result
        assert "Paragraph." in result
        assert "## References" in result
        assert "Ref content." in result
        assert "- [B](<B.md>)" in result
        assert "- [A](<A.md>)" not in result

    def test_removes_section_heading_preserves_next_heading(self) -> None:
        """When last link removed, ## Related heading goes but next heading stays."""
        content = (
            "# Title\n\nContent.\n\n"
            "## Related\n\n"
            "- [Only](<Only.md>)\n\n"
            "## References\n\nSome refs.\n"
        )
        result = remove_link_from_content(
            content=content, target_path=Path("Only.md"),
        )
        assert "## Related" not in result
        assert "## References" in result
        assert "Some refs." in result
