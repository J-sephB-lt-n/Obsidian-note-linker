"""Tests for the Related section parser."""

from pathlib import Path

from obsidian_note_linker.domain.related_section_parser import (
    IncompleteLink,
    get_existing_link_pairs,
    get_incomplete_link_pairs,
    parse_related_links,
)


class TestParseRelatedLinks:
    """Tests for parsing links from a note's ## Related section."""

    def test_extracts_obsidian_links(self) -> None:
        content = (
            "# My Note\n\nSome content.\n\n"
            "## Related\n\n"
            "- [Alpha Note](<Alpha%20Note.md>)\n"
            "- [Beta Note](<Beta%20Note.md>)\n"
        )
        links = parse_related_links(content)
        assert links == [Path("Alpha Note.md"), Path("Beta Note.md")]

    def test_no_related_section(self) -> None:
        content = "# My Note\n\nJust some content.\n"
        assert parse_related_links(content) == []

    def test_empty_related_section(self) -> None:
        content = "# My Note\n\n## Related\n\n## Another Section\n"
        assert parse_related_links(content) == []

    def test_related_section_at_end_of_file(self) -> None:
        content = (
            "# My Note\n\nContent here.\n\n"
            "## Related\n\n"
            "- [Other Note](<Other%20Note.md>)\n"
        )
        links = parse_related_links(content)
        assert links == [Path("Other Note.md")]

    def test_url_decoded_path(self) -> None:
        """Percent-encoded spaces should be decoded in the returned path."""
        content = (
            "## Related\n\n"
            "- [A Long Title](<A%20Long%20Title.md>)\n"
        )
        links = parse_related_links(content)
        assert links == [Path("A Long Title.md")]

    def test_link_in_subdirectory(self) -> None:
        content = (
            "## Related\n\n"
            "- [Sub Note](<subfolder/Sub%20Note.md>)\n"
        )
        links = parse_related_links(content)
        assert links == [Path("subfolder/Sub Note.md")]

    def test_ignores_links_outside_related_section(self) -> None:
        content = (
            "# My Note\n\n"
            "- [Body Link](<Body%20Link.md>)\n\n"
            "## Related\n\n"
            "- [Related Link](<Related%20Link.md>)\n\n"
            "## Other Section\n\n"
            "- [Other Link](<Other%20Link.md>)\n"
        )
        links = parse_related_links(content)
        assert links == [Path("Related Link.md")]

    def test_stops_at_next_heading(self) -> None:
        content = (
            "## Related\n\n"
            "- [Link A](<Link%20A.md>)\n\n"
            "## References\n\n"
            "- [Link B](<Link%20B.md>)\n"
        )
        links = parse_related_links(content)
        assert links == [Path("Link A.md")]

    def test_handles_no_percent_encoding(self) -> None:
        """Links without special characters should parse correctly."""
        content = (
            "## Related\n\n"
            "- [Simple](<Simple.md>)\n"
        )
        links = parse_related_links(content)
        assert links == [Path("Simple.md")]


class TestGetExistingLinkPairs:
    """Tests for extracting bidirectional link pairs from multiple notes."""

    def test_bidirectional_pair_detected(self) -> None:
        notes = {
            Path("a.md"): "## Related\n\n- [B](<b.md>)\n",
            Path("b.md"): "## Related\n\n- [A](<a.md>)\n",
        }
        pairs = get_existing_link_pairs(notes)
        assert (Path("a.md"), Path("b.md")) in pairs

    def test_unidirectional_link_not_included(self) -> None:
        """Only bidirectional links (both directions) form a pair."""
        notes = {
            Path("a.md"): "## Related\n\n- [B](<b.md>)\n",
            Path("b.md"): "# B Note\n\nNo related section.\n",
        }
        pairs = get_existing_link_pairs(notes)
        assert len(pairs) == 0

    def test_empty_notes(self) -> None:
        pairs = get_existing_link_pairs({})
        assert pairs == set()

    def test_pair_key_is_sorted(self) -> None:
        """Pair keys should be sorted tuples for canonical representation."""
        notes = {
            Path("z.md"): "## Related\n\n- [A](<a.md>)\n",
            Path("a.md"): "## Related\n\n- [Z](<z.md>)\n",
        }
        pairs = get_existing_link_pairs(notes)
        assert (Path("a.md"), Path("z.md")) in pairs

    def test_multiple_pairs(self) -> None:
        notes = {
            Path("a.md"): "## Related\n\n- [B](<b.md>)\n- [C](<c.md>)\n",
            Path("b.md"): "## Related\n\n- [A](<a.md>)\n",
            Path("c.md"): "## Related\n\n- [A](<a.md>)\n",
        }
        pairs = get_existing_link_pairs(notes)
        assert len(pairs) == 2
        assert (Path("a.md"), Path("b.md")) in pairs
        assert (Path("a.md"), Path("c.md")) in pairs


class TestGetIncompleteLinkPairs:
    """Tests for detecting one-directional links in ## Related sections."""

    def test_detects_one_directional_link(self) -> None:
        """A links to B but B doesn't link back → incomplete."""
        notes = {
            Path("a.md"): "## Related\n\n- [B](<b.md>)\n",
            Path("b.md"): "# B Note\n\nNo related section.\n",
        }
        result = get_incomplete_link_pairs(notes)
        assert result == [IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md"))]

    def test_bidirectional_links_are_not_incomplete(self) -> None:
        """Both notes link to each other → not incomplete."""
        notes = {
            Path("a.md"): "## Related\n\n- [B](<b.md>)\n",
            Path("b.md"): "## Related\n\n- [A](<a.md>)\n",
        }
        result = get_incomplete_link_pairs(notes)
        assert result == []

    def test_no_related_sections(self) -> None:
        notes = {
            Path("a.md"): "# A Note\n\nContent.\n",
            Path("b.md"): "# B Note\n\nContent.\n",
        }
        result = get_incomplete_link_pairs(notes)
        assert result == []

    def test_empty_notes(self) -> None:
        result = get_incomplete_link_pairs({})
        assert result == []

    def test_target_not_in_vault_is_excluded(self) -> None:
        """A links to B, but B doesn't exist as a vault note → not returned."""
        notes = {
            Path("a.md"): "## Related\n\n- [B](<b.md>)\n",
        }
        result = get_incomplete_link_pairs(notes)
        assert result == []

    def test_multiple_incomplete_links(self) -> None:
        """Multiple one-directional links detected."""
        notes = {
            Path("a.md"): "## Related\n\n- [B](<b.md>)\n- [C](<c.md>)\n",
            Path("b.md"): "# B Note\n",
            Path("c.md"): "# C Note\n",
        }
        result = get_incomplete_link_pairs(notes)
        assert len(result) == 2
        assert IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md")) in result
        assert IncompleteLink(source_path=Path("a.md"), target_path=Path("c.md")) in result

    def test_mixed_complete_and_incomplete(self) -> None:
        """A links to B (bidirectional) and C (one-way) → only C incomplete."""
        notes = {
            Path("a.md"): "## Related\n\n- [B](<b.md>)\n- [C](<c.md>)\n",
            Path("b.md"): "## Related\n\n- [A](<a.md>)\n",
            Path("c.md"): "# C Note\n",
        }
        result = get_incomplete_link_pairs(notes)
        assert result == [IncompleteLink(source_path=Path("a.md"), target_path=Path("c.md"))]

    def test_sorted_by_source_then_target(self) -> None:
        """Results are sorted by source path, then target path."""
        notes = {
            Path("z.md"): "## Related\n\n- [A](<a.md>)\n",
            Path("a.md"): "## Related\n\n- [Z](<z.md>)\n- [B](<b.md>)\n",
            Path("b.md"): "# B Note\n",
        }
        result = get_incomplete_link_pairs(notes)
        # a.md→b.md is incomplete (b.md has no Related section)
        # a.md→z.md is bidirectional (z.md links back to a.md)
        # z.md→a.md is bidirectional (a.md links back to z.md)
        assert result == [IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md"))]

    def test_handles_percent_encoded_paths(self) -> None:
        notes = {
            Path("My Note.md"): "## Related\n\n- [Other Note](<Other%20Note.md>)\n",
            Path("Other Note.md"): "# Other\n\nNo related.\n",
        }
        result = get_incomplete_link_pairs(notes)
        assert result == [
            IncompleteLink(source_path=Path("My Note.md"), target_path=Path("Other Note.md")),
        ]

    def test_handles_subdirectory_paths(self) -> None:
        notes = {
            Path("a.md"): "## Related\n\n- [Sub](<sub/note.md>)\n",
            Path("sub/note.md"): "# Sub Note\n",
        }
        result = get_incomplete_link_pairs(notes)
        assert result == [
            IncompleteLink(source_path=Path("a.md"), target_path=Path("sub/note.md")),
        ]
