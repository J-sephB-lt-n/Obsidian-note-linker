"""Markdown-to-HTML renderer using mistune.

Renders raw Obsidian markdown content to HTML for display in the
review interface.
"""

import mistune


_renderer = mistune.create_markdown()


def render_markdown(content: str) -> str:
    """Render markdown content to an HTML string.

    Args:
        content: Raw markdown text.

    Returns:
        Rendered HTML string.
    """
    if not content:
        return ""
    result = _renderer(content)
    assert isinstance(result, str), "Expected mistune to return a string"
    return result
