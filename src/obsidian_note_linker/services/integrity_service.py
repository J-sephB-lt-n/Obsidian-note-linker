"""Link integrity service — detect and resolve incomplete bidirectional links.

Identifies one-directional links in ``## Related`` sections (A links to B
but B does not link back) and provides resolution workflows: either
complete the link (add B→A) or remove the link (delete A→B).  All
resolution actions follow FR3 safety requirements (diff preview,
per-note confirmation, atomic writes, audit log).
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine

from obsidian_note_linker.domain.link_builder import (
    compute_content_diff,
    format_obsidian_link,
    insert_links_into_content,
    remove_link_from_content,
)
from obsidian_note_linker.domain.note import compute_content_hash
from obsidian_note_linker.domain.related_section_parser import (
    IncompleteLink,
    get_incomplete_link_pairs,
)
from obsidian_note_linker.infrastructure.audit_store import save_audit_entry
from obsidian_note_linker.infrastructure.file_writer import atomic_write
from obsidian_note_linker.infrastructure.vault_scanner import scan_vault

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolutionPreview:
    """Preview of a resolution action for an incomplete link.

    Attributes:
        source_path: Note that has the one-directional link.
        target_path: Note that does not link back.
        source_title: Human-readable title of the source note.
        target_title: Human-readable title of the target note.
        action: Resolution action (``"complete"`` or ``"remove"``).
        diff: Unified diff showing the proposed change.
        modified_note_path: Which note will be modified by this action.
    """

    source_path: Path
    target_path: Path
    source_title: str
    target_title: str
    action: str
    diff: str
    modified_note_path: Path


def detect_incomplete_links(vault_path: Path) -> list[IncompleteLink]:
    """Scan a vault and return all incomplete bidirectional links.

    An incomplete link exists when note A links to note B in its
    ``## Related`` section but B does not link back to A, and both
    notes exist in the vault.

    Args:
        vault_path: Absolute path to the Obsidian vault.

    Returns:
        Sorted list of ``IncompleteLink`` instances.
    """
    notes = scan_vault(vault_path)
    notes_by_path: dict[Path, str] = {
        note.relative_path: note.content for note in notes
    }
    return get_incomplete_link_pairs(notes_by_path)


class IntegrityService:
    """Orchestrates resolution of incomplete bidirectional links.

    Provides preview and apply methods for both resolution actions:
    completing a link (adding the missing reverse link) and removing
    a link (deleting the existing one-directional link).

    Args:
        engine: SQLAlchemy engine for audit log access.
        vault_path: Absolute path to the Obsidian vault.
    """

    def __init__(self, engine: Engine, vault_path: Path) -> None:
        self._engine = engine
        self._vault_path = vault_path

    def preview_complete(
        self,
        source_path: Path,
        target_path: Path,
    ) -> ResolutionPreview:
        """Generate a diff preview for completing an incomplete link.

        Completing means adding a link from ``target_path`` back to
        ``source_path`` in the target note's ``## Related`` section.

        Args:
            source_path: Note that has the existing link.
            target_path: Note that will receive the new reverse link.

        Returns:
            ResolutionPreview with diff for the target note.

        Raises:
            FileNotFoundError: If the target note does not exist on disk.
        """
        target_content = self._read_note(target_path)
        link_to_source = format_obsidian_link(source_path)
        modified = insert_links_into_content(
            content=target_content, links=[link_to_source],
        )
        diff = compute_content_diff(
            original=target_content, modified=modified, filename=str(target_path),
        )

        return ResolutionPreview(
            source_path=source_path,
            target_path=target_path,
            source_title=source_path.stem,
            target_title=target_path.stem,
            action="complete",
            diff=diff,
            modified_note_path=target_path,
        )

    def preview_remove(
        self,
        source_path: Path,
        target_path: Path,
    ) -> ResolutionPreview:
        """Generate a diff preview for removing an incomplete link.

        Removing means deleting the link from ``source_path`` to
        ``target_path`` in the source note's ``## Related`` section.

        Args:
            source_path: Note that contains the link to remove.
            target_path: Note that the link points to.

        Returns:
            ResolutionPreview with diff for the source note.

        Raises:
            FileNotFoundError: If the source note does not exist on disk.
        """
        source_content = self._read_note(source_path)
        modified = remove_link_from_content(
            content=source_content, target_path=target_path,
        )
        diff = compute_content_diff(
            original=source_content, modified=modified, filename=str(source_path),
        )

        return ResolutionPreview(
            source_path=source_path,
            target_path=target_path,
            source_title=source_path.stem,
            target_title=target_path.stem,
            action="remove",
            diff=diff,
            modified_note_path=source_path,
        )

    def apply_complete(
        self,
        source_path: Path,
        target_path: Path,
    ) -> None:
        """Complete an incomplete link by adding the missing reverse link.

        Reads the target note, inserts a link back to the source,
        writes atomically, and records an audit entry.

        Args:
            source_path: Note that has the existing link.
            target_path: Note that will receive the new reverse link.

        Raises:
            FileNotFoundError: If the target note does not exist on disk.
        """
        target_content = self._read_note(target_path)
        link_to_source = format_obsidian_link(source_path)
        modified = insert_links_into_content(
            content=target_content, links=[link_to_source],
        )

        if modified != target_content:
            self._write_and_audit(
                note_path=target_path,
                original=target_content,
                modified=modified,
                action="COMPLETE_LINK",
                detail=(
                    f"Completed link from {source_path.stem} — "
                    f"added reverse link to {source_path}"
                ),
            )

        logger.info(
            "Completed link: %s → %s (added reverse in %s)",
            source_path, target_path, target_path,
        )

    def apply_remove(
        self,
        source_path: Path,
        target_path: Path,
    ) -> None:
        """Remove an incomplete link from the source note.

        Reads the source note, removes the link to the target,
        writes atomically, and records an audit entry.

        Args:
            source_path: Note that contains the link to remove.
            target_path: Note that the link points to.

        Raises:
            FileNotFoundError: If the source note does not exist on disk.
        """
        source_content = self._read_note(source_path)
        modified = remove_link_from_content(
            content=source_content, target_path=target_path,
        )

        if modified != source_content:
            self._write_and_audit(
                note_path=source_path,
                original=source_content,
                modified=modified,
                action="REMOVE_LINK",
                detail=(
                    f"Removed one-way link to {target_path.stem} ({target_path})"
                ),
            )

        logger.info(
            "Removed link: %s → %s (removed from %s)",
            source_path, target_path, source_path,
        )

    def _read_note(self, relative_path: Path) -> str:
        """Read a note file from the vault.

        Args:
            relative_path: Path relative to the vault root.

        Returns:
            Raw file content as a string.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        full_path = self._vault_path / relative_path
        if not full_path.is_file():
            raise FileNotFoundError(f"Note not found: {full_path}")
        return full_path.read_text(encoding="utf-8")

    def _write_and_audit(
        self,
        note_path: Path,
        original: str,
        modified: str,
        action: str,
        detail: str,
    ) -> None:
        """Write modified content and create an audit entry.

        Args:
            note_path: Relative path of the note being modified.
            original: Original file content.
            modified: Modified file content.
            action: Audit action type (e.g. ``"COMPLETE_LINK"``).
            detail: Human-readable description of the change.
        """
        full_path = self._vault_path / note_path

        hash_before = compute_content_hash(original)
        hash_after = compute_content_hash(modified)

        atomic_write(path=full_path, content=modified)

        save_audit_entry(
            engine=self._engine,
            note_path=str(note_path),
            action=action,
            detail=detail,
            content_hash_before=hash_before,
            content_hash_after=hash_after,
        )
