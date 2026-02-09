"""Document search domain models and utilities.

Provides the SearchMode enum, SearchResult dataclass, and snippet
generation for the document search feature.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from obsidian_note_linker.domain.markdown_stripper import strip_markdown


class SearchMode(Enum):
    """Available document search modes.

    Attributes:
        FTS: Full-text search using BM25 lexical ranking.
        SEMANTIC: Semantic search using embedding cosine similarity.
        HYBRID: Hybrid search combining FTS and semantic via RRF.
    """

    FTS = "fts"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class SearchResult:
    """A single document search result.

    Attributes:
        relative_path: Path of the note relative to the vault root.
        title: Display title of the note (filename without extension).
        score: Relevance score (higher is more relevant).
        snippet: Plain-text preview of the note content.
    """

    relative_path: Path
    title: str
    score: float
    snippet: str


def generate_snippet(content: str, max_length: int = 200) -> str:
    """Generate a plain-text snippet from raw markdown content.

    Strips markdown formatting and truncates at a word boundary
    if the result exceeds ``max_length``.

    Args:
        content: Raw markdown content of a note.
        max_length: Maximum number of characters before truncation.

    Returns:
        Plain-text snippet, with ``...`` appended if truncated.
    """
    stripped = strip_markdown(content)

    if len(stripped) <= max_length:
        return stripped

    truncated = stripped[:max_length].rsplit(" ", 1)[0]
    return truncated + "..."
