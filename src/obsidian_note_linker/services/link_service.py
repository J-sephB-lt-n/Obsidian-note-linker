"""Link application service — orchestrates safe bidirectional link creation.

Coordinates the full link-application workflow: identifying approved
pairs, generating diff previews, writing links atomically, and
recording audit entries.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine

from obsidian_note_linker.domain.link_builder import (
    compute_content_diff,
    format_obsidian_link,
    insert_links_into_content,
)
from obsidian_note_linker.domain.note import compute_content_hash
from obsidian_note_linker.infrastructure.audit_store import save_audit_entry
from obsidian_note_linker.infrastructure.decision_store import (
    get_pending_approved_pairs,
    mark_decision_applied,
)
from obsidian_note_linker.infrastructure.file_writer import atomic_write
from obsidian_note_linker.infrastructure.models import DecisionRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PairDiffPreview:
    """Preview of changes to be made for a single approved pair.

    Attributes:
        note_a_path: Relative path of the first note.
        note_b_path: Relative path of the second note.
        note_a_title: Human-readable title of note A.
        note_b_title: Human-readable title of note B.
        note_a_diff: Unified diff for note A (empty if no changes needed).
        note_b_diff: Unified diff for note B (empty if no changes needed).
    """

    note_a_path: Path
    note_b_path: Path
    note_a_title: str
    note_b_title: str
    note_a_diff: str
    note_b_diff: str

    @property
    def has_changes(self) -> bool:
        """Whether either note requires modification."""
        return bool(self.note_a_diff or self.note_b_diff)


class LinkService:
    """Orchestrates the safe application of bidirectional links.

    Handles the full workflow: retrieving pending approved pairs,
    generating diff previews, applying links atomically, and
    recording audit entries.

    Args:
        engine: SQLAlchemy engine for database access.
        vault_path: Absolute path to the Obsidian vault.
    """

    def __init__(self, engine: Engine, vault_path: Path) -> None:
        self._engine = engine
        self._vault_path = vault_path

    def get_pending_pairs(self) -> list[DecisionRecord]:
        """Get all approved pairs that haven't been applied yet.

        Returns:
            List of unapplied YES DecisionRecords.
        """
        pending = get_pending_approved_pairs(engine=self._engine)
        logger.debug("Found %d pending approved pair(s)", len(pending))
        return pending

    def preview_pair(self, decision: DecisionRecord) -> PairDiffPreview:
        """Generate a diff preview for an approved pair.

        Reads both notes from disk, computes what the content would look
        like after inserting the bidirectional links, and returns unified
        diffs for each note.

        Args:
            decision: The DecisionRecord for the approved pair.

        Returns:
            PairDiffPreview with diffs for both notes.

        Raises:
            FileNotFoundError: If either note file does not exist on disk.
        """
        path_a = Path(decision.note_a_path)
        path_b = Path(decision.note_b_path)

        content_a = self._read_note(path_a)
        content_b = self._read_note(path_b)

        link_a_to_b = format_obsidian_link(path_b)
        link_b_to_a = format_obsidian_link(path_a)

        modified_a = insert_links_into_content(
            content=content_a, links=[link_a_to_b],
        )
        modified_b = insert_links_into_content(
            content=content_b, links=[link_b_to_a],
        )

        diff_a = compute_content_diff(
            original=content_a,
            modified=modified_a,
            filename=str(path_a),
        )
        diff_b = compute_content_diff(
            original=content_b,
            modified=modified_b,
            filename=str(path_b),
        )

        return PairDiffPreview(
            note_a_path=path_a,
            note_b_path=path_b,
            note_a_title=path_a.stem,
            note_b_title=path_b.stem,
            note_a_diff=diff_a,
            note_b_diff=diff_b,
        )

    def apply_pair(self, decision: DecisionRecord) -> None:
        """Apply bidirectional links for an approved pair.

        Reads both notes, inserts links, writes atomically, creates
        audit entries, and marks the decision as applied.

        Args:
            decision: The DecisionRecord for the approved pair.

        Raises:
            FileNotFoundError: If either note file does not exist on disk.
        """
        path_a = Path(decision.note_a_path)
        path_b = Path(decision.note_b_path)

        content_a = self._read_note(path_a)
        content_b = self._read_note(path_b)

        link_a_to_b = format_obsidian_link(path_b)
        link_b_to_a = format_obsidian_link(path_a)

        modified_a = insert_links_into_content(
            content=content_a, links=[link_a_to_b],
        )
        modified_b = insert_links_into_content(
            content=content_b, links=[link_b_to_a],
        )

        # Write note A if changed
        if modified_a != content_a:
            self._write_and_audit(
                note_path=path_a,
                original=content_a,
                modified=modified_a,
                linked_to=path_b,
            )

        # Write note B if changed
        if modified_b != content_b:
            self._write_and_audit(
                note_path=path_b,
                original=content_b,
                modified=modified_b,
                linked_to=path_a,
            )

        # Mark the decision as applied
        mark_decision_applied(
            engine=self._engine,
            note_a_path=decision.note_a_path,
            note_b_path=decision.note_b_path,
        )

        logger.info(
            "Applied links: %s <-> %s",
            decision.note_a_path, decision.note_b_path,
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
        linked_to: Path,
    ) -> None:
        """Write modified content and create an audit entry.

        Args:
            note_path: Relative path of the note being modified.
            original: Original file content.
            modified: Modified file content.
            linked_to: Path of the note being linked to.
        """
        full_path = self._vault_path / note_path

        hash_before = compute_content_hash(original)
        hash_after = compute_content_hash(modified)

        atomic_write(path=full_path, content=modified)
        logger.info("Wrote modified note: %s (linked to %s)", note_path, linked_to)

        save_audit_entry(
            engine=self._engine,
            note_path=str(note_path),
            action="ADD_LINK",
            detail=f"Added link to {linked_to.stem} ({linked_to})",
            content_hash_before=hash_before,
            content_hash_after=hash_after,
        )
