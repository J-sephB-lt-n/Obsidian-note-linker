"""Tests for markdown stripping utilities."""

from obsidian_note_linker.domain.markdown_stripper import (
    prepare_note_for_embedding,
    strip_markdown,
)


class TestStripMarkdown:
    """Tests for markdown formatting removal."""

    def test_plain_text_unchanged(self) -> None:
        assert strip_markdown("Hello world") == "Hello world"

    def test_removes_yaml_frontmatter(self) -> None:
        text = "---\ntitle: Test\ntags: [a, b]\n---\nContent here"

        assert strip_markdown(text) == "Content here"

    def test_removes_fenced_code_blocks(self) -> None:
        text = "Before\n```python\ndef foo():\n    pass\n```\nAfter"

        result = strip_markdown(text)
        assert "Before" in result
        assert "After" in result
        assert "def foo" not in result

    def test_preserves_inline_code_content(self) -> None:
        assert strip_markdown("Use `pip install`") == "Use pip install"

    def test_removes_markdown_images(self) -> None:
        assert strip_markdown("![alt text](image.png)").strip() == ""

    def test_removes_obsidian_embeds(self) -> None:
        assert strip_markdown("![[embedded note]]").strip() == ""

    def test_converts_wikilinks_to_text(self) -> None:
        assert strip_markdown("See [[My Note]]") == "See My Note"

    def test_converts_wikilinks_with_alias(self) -> None:
        assert strip_markdown("See [[My Note|custom text]]") == "See custom text"

    def test_converts_markdown_links_to_text(self) -> None:
        assert strip_markdown("[Click here](https://example.com)") == "Click here"

    def test_removes_header_markers(self) -> None:
        text = "# Title\n## Subtitle\n### Section"
        result = strip_markdown(text)

        assert "Title" in result
        assert "Subtitle" in result
        assert "#" not in result

    def test_removes_bold_markers(self) -> None:
        assert strip_markdown("This is **bold** text") == "This is bold text"

    def test_removes_italic_markers(self) -> None:
        assert strip_markdown("This is *italic* text") == "This is italic text"

    def test_removes_strikethrough(self) -> None:
        assert strip_markdown("This is ~~deleted~~ text") == "This is deleted text"

    def test_removes_blockquote_markers(self) -> None:
        assert strip_markdown("> Quoted text") == "Quoted text"

    def test_removes_unordered_list_markers(self) -> None:
        text = "- Item one\n- Item two\n* Item three"
        result = strip_markdown(text)

        assert "Item one" in result
        assert "Item two" in result
        assert "Item three" in result
        assert not result.startswith("-")

    def test_removes_ordered_list_markers(self) -> None:
        text = "1. First\n2. Second"
        result = strip_markdown(text)

        assert "First" in result
        assert "Second" in result

    def test_removes_horizontal_rules(self) -> None:
        text = "Above\n\n---\n\nBelow"
        result = strip_markdown(text)

        assert "Above" in result
        assert "Below" in result
        assert "---" not in result

    def test_removes_html_tags(self) -> None:
        result = strip_markdown("Text <br> more <b>bold</b>")

        assert "Text" in result
        assert "bold" in result
        assert "<" not in result

    def test_collapses_excessive_blank_lines(self) -> None:
        text = "Para one\n\n\n\n\nPara two"

        assert strip_markdown(text) == "Para one\n\nPara two"

    def test_empty_string(self) -> None:
        assert strip_markdown("") == ""

    def test_only_frontmatter(self) -> None:
        assert strip_markdown("---\ntitle: Test\n---") == ""


class TestPrepareNoteForEmbedding:
    """Tests for note text preparation for embedding."""

    def test_prepends_title_to_content(self) -> None:
        result = prepare_note_for_embedding(title="My Note", content="Some content")

        assert result.startswith("My Note\n\n"), "Should prepend title with blank line"
        assert "Some content" in result

    def test_strips_markdown_from_content(self) -> None:
        result = prepare_note_for_embedding(
            title="Title",
            content="# Header\n\n**Bold** text",
        )

        assert "#" not in result, "Should strip header markers"
        assert "**" not in result, "Should strip bold markers"
        assert "Header" in result
        assert "Bold text" in result

    def test_returns_title_only_when_content_empty(self) -> None:
        assert prepare_note_for_embedding(title="Title", content="") == "Title"

    def test_returns_title_only_when_content_is_frontmatter_only(self) -> None:
        result = prepare_note_for_embedding(
            title="Title",
            content="---\ntitle: x\n---",
        )

        assert result == "Title"
