"""Markdown stripping utilities for text preparation.

Provides functions to strip markdown formatting from text (producing plain
text suitable for embedding) and to prepare note content for the embedding
pipeline by prepending the note title.
"""

import re


def strip_markdown(text: str) -> str:
    """Strip markdown formatting from text, returning plain text.

    Processing order is chosen to avoid interactions between patterns
    (e.g. code blocks are removed before processing links inside them).

    Args:
        text: Raw markdown text.

    Returns:
        Plain text with markdown formatting removed.
    """
    result = text

    # 1. Remove YAML frontmatter
    result = re.sub(r"^---\n.*?\n---\n?", "", result, count=1, flags=re.DOTALL)

    # 2. Remove fenced code blocks (entire block including content)
    result = re.sub(r"```[^\n]*\n.*?```", "", result, flags=re.DOTALL)

    # 3. Remove inline code backticks (keep content inside)
    result = re.sub(r"`([^`]*)`", r"\1", result)

    # 4. Remove images — Obsidian embeds and standard markdown
    result = re.sub(r"!\[\[.*?\]\]", "", result)
    result = re.sub(r"!\[.*?\]\(.*?\)", "", result)

    # 5. Convert Obsidian wikilinks to plain text
    # [[Page Name|Display Text]] → Display Text
    result = re.sub(r"\[\[([^|\]]*)\|([^\]]*)\]\]", r"\2", result)
    # [[Page Name]] → Page Name
    result = re.sub(r"\[\[([^\]]*)\]\]", r"\1", result)

    # 6. Convert standard markdown links to text
    result = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", result)

    # 7. Remove header markers (keep the heading text)
    result = re.sub(r"^#{1,6}\s+", "", result, flags=re.MULTILINE)

    # 8. Remove bold/italic markers (keep the text)
    result = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", result)
    result = re.sub(r"_{1,3}(.*?)_{1,3}", r"\1", result)

    # 9. Remove strikethrough
    result = re.sub(r"~~(.*?)~~", r"\1", result)

    # 10. Remove blockquote markers
    result = re.sub(r"^>\s?", "", result, flags=re.MULTILINE)

    # 11. Remove unordered list markers
    result = re.sub(r"^(\s*)[-*+]\s+", r"\1", result, flags=re.MULTILINE)

    # 12. Remove ordered list markers
    result = re.sub(r"^(\s*)\d+\.\s+", r"\1", result, flags=re.MULTILINE)

    # 13. Remove horizontal rules
    result = re.sub(r"^[-*_]{3,}\s*$", "", result, flags=re.MULTILINE)

    # 14. Remove HTML tags
    result = re.sub(r"<[^>]+>", "", result)

    # 15. Collapse multiple blank lines into one
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


def prepare_note_for_embedding(title: str, content: str) -> str:
    """Prepare note text for embedding by stripping markdown and prepending title.

    The title is prepended to provide a strong topical signal for the
    embedding model, separated from the body by a blank line.

    Args:
        title: Note title (typically the filename without ``.md`` extension).
        content: Raw markdown content of the note.

    Returns:
        Clean plain text suitable for embedding, with title prepended.
    """
    stripped = strip_markdown(content)
    if stripped:
        return f"{title}\n\n{stripped}"
    return title
