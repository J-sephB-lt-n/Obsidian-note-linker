"""Tests for the markdown renderer."""

from obsidian_note_linker.infrastructure.markdown_renderer import render_markdown


class TestRenderMarkdown:
    """Tests for render_markdown()."""

    def test_renders_heading(self) -> None:
        result = render_markdown("# Hello World")
        assert "<h1>" in result
        assert "Hello World" in result

    def test_renders_paragraph(self) -> None:
        result = render_markdown("This is a paragraph.")
        assert "<p>" in result
        assert "This is a paragraph." in result

    def test_renders_bold_and_italic(self) -> None:
        result = render_markdown("**bold** and *italic*")
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result

    def test_renders_code_block(self) -> None:
        result = render_markdown("```python\nprint('hi')\n```")
        assert "<code" in result
        assert "print" in result

    def test_renders_inline_code(self) -> None:
        result = render_markdown("Use `foo()` here.")
        assert "<code>foo()</code>" in result

    def test_renders_unordered_list(self) -> None:
        result = render_markdown("- item one\n- item two")
        assert "<li>" in result
        assert "item one" in result

    def test_renders_link(self) -> None:
        result = render_markdown("[click](http://example.com)")
        assert "<a" in result
        assert "http://example.com" in result

    def test_renders_blockquote(self) -> None:
        result = render_markdown("> quoted text")
        assert "<blockquote>" in result
        assert "quoted text" in result

    def test_empty_content_returns_empty_string(self) -> None:
        result = render_markdown("")
        assert result.strip() == ""

    def test_returns_string(self) -> None:
        result = render_markdown("# Test")
        assert isinstance(result, str)

    def test_renders_multiple_headings(self) -> None:
        result = render_markdown("# H1\n## H2\n### H3")
        assert "<h1>" in result
        assert "<h2>" in result
        assert "<h3>" in result
