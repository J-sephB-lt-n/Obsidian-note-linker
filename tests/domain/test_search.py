"""Tests for document search domain models and utilities."""

from pathlib import Path

from obsidian_note_linker.domain.search import (
    SearchMode,
    SearchResult,
    generate_snippet,
)


class TestSearchMode:
    """Tests for the SearchMode enum."""

    def test_fts_value(self) -> None:
        assert SearchMode.FTS.value == "fts"

    def test_semantic_value(self) -> None:
        assert SearchMode.SEMANTIC.value == "semantic"

    def test_hybrid_value(self) -> None:
        assert SearchMode.HYBRID.value == "hybrid"

    def test_from_string(self) -> None:
        assert SearchMode("fts") is SearchMode.FTS
        assert SearchMode("semantic") is SearchMode.SEMANTIC
        assert SearchMode("hybrid") is SearchMode.HYBRID


class TestSearchResult:
    """Tests for the SearchResult frozen dataclass."""

    def test_create_result(self) -> None:
        result = SearchResult(
            relative_path=Path("notes/my-note.md"),
            title="My Note",
            score=0.85,
            snippet="This is a snippet of text...",
        )
        assert result.relative_path == Path("notes/my-note.md")
        assert result.title == "My Note"
        assert result.score == 0.85
        assert result.snippet == "This is a snippet of text..."

    def test_result_is_frozen(self) -> None:
        result = SearchResult(
            relative_path=Path("test.md"),
            title="Test",
            score=0.5,
            snippet="snippet",
        )
        try:
            result.score = 0.9  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass


class TestGenerateSnippet:
    """Tests for the generate_snippet utility."""

    def test_short_content_returned_unchanged(self) -> None:
        content = "A short note."
        assert generate_snippet(content) == "A short note."

    def test_long_content_truncated_with_ellipsis(self) -> None:
        content = "word " * 100  # 500 characters
        snippet = generate_snippet(content, max_length=50)
        assert len(snippet) <= 53  # 50 + "..."
        assert snippet.endswith("...")

    def test_truncation_at_word_boundary(self) -> None:
        content = "The quick brown fox jumps over the lazy dog near the river"
        snippet = generate_snippet(content, max_length=30)
        assert snippet.endswith("...")
        # Should not cut mid-word
        text_part = snippet[:-3]
        assert not text_part.endswith(" ")  # no trailing space before ...

    def test_markdown_stripped_before_snippet(self) -> None:
        content = "# Heading\n\n**Bold text** and [a link](http://example.com)"
        snippet = generate_snippet(content)
        assert "#" not in snippet
        assert "**" not in snippet
        assert "http" not in snippet
        assert "Bold text" in snippet
        assert "a link" in snippet

    def test_empty_content(self) -> None:
        assert generate_snippet("") == ""

    def test_frontmatter_stripped(self) -> None:
        content = "---\ntitle: Test\ntags: [a, b]\n---\n\nActual content here."
        snippet = generate_snippet(content)
        assert "title: Test" not in snippet
        assert "Actual content here." in snippet

    def test_default_max_length(self) -> None:
        """Default max_length is 200."""
        content = "x " * 200  # 400 characters
        snippet = generate_snippet(content)
        assert len(snippet) <= 203  # 200 + "..."

    def test_exact_boundary_no_ellipsis(self) -> None:
        """Content exactly at max_length should not have ellipsis."""
        content = "abcde"
        snippet = generate_snippet(content, max_length=5)
        assert snippet == "abcde"
