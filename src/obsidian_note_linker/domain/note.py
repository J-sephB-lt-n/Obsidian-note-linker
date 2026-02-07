"""Note domain model and content hashing."""

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Note:
    """Represents a single Obsidian markdown note.

    Attributes:
        relative_path: Path relative to vault root (e.g. ``notes/my-note.md``).
        content: Raw markdown content of the note file.
        content_hash: SHA256 hex digest of the content.
    """

    relative_path: Path
    content: str
    content_hash: str


def compute_content_hash(content: str) -> str:
    """Compute the SHA256 hex digest of note content.

    Args:
        content: Raw text content of the note.

    Returns:
        64-character lowercase hex digest string.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
