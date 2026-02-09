"""Review service — orchestrates the human-in-the-loop review workflow.

Provides target note selection, candidate filtering, decision recording,
and note rendering for the review interface.
"""

import logging
import random
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine

from obsidian_note_linker.domain.candidate import CandidatePair
from obsidian_note_linker.infrastructure.decision_store import save_decision
from obsidian_note_linker.infrastructure.markdown_renderer import render_markdown
from obsidian_note_linker.infrastructure.note_store import get_note_record_by_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReviewTarget:
    """A note that has candidate pairs available for review.

    Attributes:
        note_path: Relative path of the target note.
        title: Human-readable title (derived from filename).
        candidate_count: Number of candidate pairs involving this note.
    """

    note_path: Path
    title: str
    candidate_count: int


class ReviewService:
    """Orchestrates the review workflow for candidate note pairs.

    Handles target note selection, candidate filtering, decision
    recording, and note reading/rendering.

    Args:
        engine: SQLAlchemy engine for database access.
        vault_path: Absolute path to the Obsidian vault.
    """

    def __init__(self, engine: Engine, vault_path: Path) -> None:
        self._engine = engine
        self._vault_path = vault_path

    def get_targets_with_candidates(
        self,
        candidates: list[CandidatePair],
    ) -> list[ReviewTarget]:
        """Group candidates by note and return target summaries.

        Each note that appears in at least one candidate pair is
        returned as a ``ReviewTarget`` with its candidate count.

        Args:
            candidates: Full list of candidate pairs.

        Returns:
            List of ReviewTarget sorted alphabetically by path.
        """
        counts: dict[Path, int] = {}
        for candidate in candidates:
            counts[candidate.note_a_path] = counts.get(candidate.note_a_path, 0) + 1
            counts[candidate.note_b_path] = counts.get(candidate.note_b_path, 0) + 1

        targets = [
            ReviewTarget(
                note_path=path,
                title=path.stem,
                candidate_count=count,
            )
            for path, count in counts.items()
        ]
        targets.sort(key=lambda t: t.note_path)
        logger.debug(
            "Found %d review targets from %d candidates",
            len(targets), len(candidates),
        )
        return targets

    def get_candidates_for_target(
        self,
        candidates: list[CandidatePair],
        target: Path,
        skipped_pair_keys: set[tuple[Path, Path]] | None = None,
    ) -> list[CandidatePair]:
        """Get candidates for a specific target note.

        Filters the candidate list to pairs involving the target note,
        excludes skipped pairs, and sorts by RRF score descending.

        Args:
            candidates: Full list of candidate pairs.
            target: Relative path of the target note.
            skipped_pair_keys: Set of canonical pair keys to exclude
                (pairs the user has skipped in the current session).

        Returns:
            Filtered and sorted list of candidate pairs.
        """
        skipped = skipped_pair_keys or set()

        result = [
            c for c in candidates
            if (target in (c.note_a_path, c.note_b_path))
            and c.pair_key not in skipped
        ]
        result.sort(key=lambda c: c.rrf_score, reverse=True)
        return result

    def get_random_target(
        self,
        candidates: list[CandidatePair],
    ) -> Path | None:
        """Pick a random target note from those with candidates.

        Args:
            candidates: Full list of candidate pairs.

        Returns:
            A randomly chosen note path, or None if no candidates.
        """
        if not candidates:
            return None

        all_paths: set[Path] = set()
        for c in candidates:
            all_paths.add(c.note_a_path)
            all_paths.add(c.note_b_path)

        return random.choice(sorted(all_paths))

    def record_decision(
        self,
        note_a_path: Path,
        note_b_path: Path,
        decision: str,
    ) -> None:
        """Record a YES or NO decision for a candidate pair.

        Looks up the current content hashes from the database and
        saves the decision.  SKIP decisions should not be passed to
        this method — they are not persisted.

        Args:
            note_a_path: Relative path of the first note.
            note_b_path: Relative path of the second note.
            decision: Decision type (``"YES"`` or ``"NO"``).

        Raises:
            AssertionError: If decision is not YES or NO.
            ValueError: If either note has no indexed record in the DB.
        """
        assert decision in ("YES", "NO"), f"Invalid decision: {decision!r}"

        record_a = get_note_record_by_path(
            self._engine, str(note_a_path),
        )
        record_b = get_note_record_by_path(
            self._engine, str(note_b_path),
        )

        if record_a is None:
            raise ValueError(
                f"No indexed record for note: {note_a_path}"
            )
        if record_b is None:
            raise ValueError(
                f"No indexed record for note: {note_b_path}"
            )

        save_decision(
            engine=self._engine,
            note_a_path=str(note_a_path),
            note_b_path=str(note_b_path),
            decision=decision,
            note_a_hash=record_a.content_hash,
            note_b_hash=record_b.content_hash,
        )

        logger.info(
            "Recorded %s decision for (%s, %s)",
            decision, note_a_path, note_b_path,
        )

    def read_and_render_note(self, note_path: Path) -> tuple[str, str]:
        """Read a note from the vault and render its markdown to HTML.

        Args:
            note_path: Relative path of the note within the vault.

        Returns:
            Tuple of ``(title, rendered_html)`` where title is the
            filename stem.

        Raises:
            FileNotFoundError: If the note file does not exist.
        """
        full_path = self._vault_path / note_path
        if not full_path.is_file():
            raise FileNotFoundError(f"Note not found: {full_path}")

        content = full_path.read_text(encoding="utf-8")
        html = render_markdown(content)
        title = note_path.stem

        return title, html
