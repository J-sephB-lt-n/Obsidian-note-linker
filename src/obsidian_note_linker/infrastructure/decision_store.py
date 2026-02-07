"""CRUD operations for DecisionRecord persistence.

Decisions record whether a human reviewer chose YES or NO for a
candidate note pair.  Each decision stores the content hashes of both
notes at the time of the decision so that stale decisions (where a
note has since been modified) can be detected and excluded.
"""

import logging
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from obsidian_note_linker.infrastructure.models import DecisionRecord

logger = logging.getLogger(__name__)


def save_decision(
    engine: Engine,
    note_a_path: str,
    note_b_path: str,
    decision: str,
    note_a_hash: str,
    note_b_hash: str,
) -> DecisionRecord:
    """Save or update a review decision for a note pair.

    Paths are stored in sorted order for canonical pair representation.
    If a decision already exists for this pair, it is updated.

    Args:
        engine: SQLAlchemy engine.
        note_a_path: Relative path of first note.
        note_b_path: Relative path of second note.
        decision: Decision type (``"YES"`` or ``"NO"``).
        note_a_hash: SHA256 content hash of note A at time of decision.
        note_b_hash: SHA256 content hash of note B at time of decision.

    Returns:
        The created or updated DecisionRecord.
    """
    assert decision in ("YES", "NO"), f"Invalid decision: {decision!r}"

    # Canonicalise path order
    sorted_paths = sorted([note_a_path, note_b_path])
    canon_a, canon_b = sorted_paths[0], sorted_paths[1]

    # Match hashes to canonical order
    if canon_a == note_a_path:
        hash_a, hash_b = note_a_hash, note_b_hash
    else:
        hash_a, hash_b = note_b_hash, note_a_hash

    with Session(engine) as session:
        existing = session.exec(
            select(DecisionRecord).where(
                DecisionRecord.note_a_path == canon_a,
                DecisionRecord.note_b_path == canon_b,
            )
        ).first()

        if existing:
            existing.decision = decision
            existing.note_a_hash = hash_a
            existing.note_b_hash = hash_b
            session.add(existing)
            session.commit()
            session.refresh(existing)
            logger.debug("Updated decision for (%s, %s): %s", canon_a, canon_b, decision)
            return existing

        record = DecisionRecord(
            note_a_path=canon_a,
            note_b_path=canon_b,
            decision=decision,
            note_a_hash=hash_a,
            note_b_hash=hash_b,
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        logger.debug("Saved decision for (%s, %s): %s", canon_a, canon_b, decision)
        return record


def get_valid_decisions(
    engine: Engine,
    current_hashes: dict[str, str],
) -> set[tuple[Path, Path]]:
    """Retrieve decisions that are still valid given current note content.

    A decision is valid when both notes still exist in the vault and
    their content hashes match the hashes recorded at decision time.
    Decisions for modified or deleted notes are excluded (they will
    reappear as candidates for review).

    Args:
        engine: SQLAlchemy engine.
        current_hashes: Mapping of ``relative_path`` → current content hash
                        for all notes currently in the vault.

    Returns:
        Set of canonically sorted ``(path_a, path_b)`` tuples for valid
        decisions.
    """
    with Session(engine) as session:
        records = session.exec(select(DecisionRecord)).all()

    valid: set[tuple[Path, Path]] = set()
    for record in records:
        current_a = current_hashes.get(record.note_a_path)
        current_b = current_hashes.get(record.note_b_path)

        if (
            current_a is not None
            and current_b is not None
            and current_a == record.note_a_hash
            and current_b == record.note_b_hash
        ):
            valid.add((Path(record.note_a_path), Path(record.note_b_path)))

    return valid
