"""Vault scanner — reads markdown files from an Obsidian vault."""

import logging
from pathlib import Path

from obsidian_note_linker.domain.note import Note, compute_content_hash

logger = logging.getLogger(__name__)

EXCLUDED_DIRS = frozenset({".obsidian", ".obsidian-linker"})


def scan_vault(vault_path: Path) -> list[Note]:
    """Scan an Obsidian vault for all markdown notes.

    Recursively finds ``.md`` files, excluding the ``.obsidian/`` and
    ``.obsidian-linker/`` directories.  For each file, reads the content
    and computes a SHA256 content hash.

    Args:
        vault_path: Absolute path to the Obsidian vault root.

    Returns:
        List of Note objects sorted by relative path.

    Raises:
        FileNotFoundError: If vault_path does not exist.
    """
    if not vault_path.exists():
        raise FileNotFoundError(f"Vault path does not exist: {vault_path}")

    notes: list[Note] = []

    for md_file in sorted(vault_path.rglob("*.md")):
        relative = md_file.relative_to(vault_path)

        if _is_excluded(relative):
            continue

        content = md_file.read_text(encoding="utf-8")
        content_hash = compute_content_hash(content)

        notes.append(
            Note(
                relative_path=relative,
                content=content,
                content_hash=content_hash,
            )
        )

    logger.info("Scanned vault: found %d notes in %s", len(notes), vault_path)
    return notes


def _is_excluded(relative_path: Path) -> bool:
    """Check whether a path falls under an excluded directory."""
    return any(part in EXCLUDED_DIRS for part in relative_path.parts)
