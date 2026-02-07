"""Tests for decision store CRUD operations."""

from pathlib import Path

from obsidian_note_linker.infrastructure.decision_store import (
    get_valid_decisions,
    save_decision,
)


class TestSaveDecision:
    """Tests for saving review decisions."""

    def test_saves_yes_decision(self, db_engine) -> None:
        save_decision(
            engine=db_engine,
            note_a_path="a.md",
            note_b_path="b.md",
            decision="YES",
            note_a_hash="hash_a",
            note_b_hash="hash_b",
        )
        # Verify via get_valid_decisions
        decisions = get_valid_decisions(
            engine=db_engine,
            current_hashes={"a.md": "hash_a", "b.md": "hash_b"},
        )
        assert (Path("a.md"), Path("b.md")) in decisions

    def test_saves_no_decision(self, db_engine) -> None:
        save_decision(
            engine=db_engine,
            note_a_path="a.md",
            note_b_path="b.md",
            decision="NO",
            note_a_hash="hash_a",
            note_b_hash="hash_b",
        )
        decisions = get_valid_decisions(
            engine=db_engine,
            current_hashes={"a.md": "hash_a", "b.md": "hash_b"},
        )
        assert (Path("a.md"), Path("b.md")) in decisions

    def test_paths_stored_in_sorted_order(self, db_engine) -> None:
        """Paths are canonicalized so (z.md, a.md) is stored as (a.md, z.md)."""
        save_decision(
            engine=db_engine,
            note_a_path="z.md",
            note_b_path="a.md",
            decision="YES",
            note_a_hash="hz",
            note_b_hash="ha",
        )
        decisions = get_valid_decisions(
            engine=db_engine,
            current_hashes={"a.md": "ha", "z.md": "hz"},
        )
        assert (Path("a.md"), Path("z.md")) in decisions

    def test_upserts_existing_decision(self, db_engine) -> None:
        """Saving a decision for an existing pair updates it."""
        save_decision(
            engine=db_engine,
            note_a_path="a.md",
            note_b_path="b.md",
            decision="YES",
            note_a_hash="h1",
            note_b_hash="h2",
        )
        save_decision(
            engine=db_engine,
            note_a_path="a.md",
            note_b_path="b.md",
            decision="NO",
            note_a_hash="h3",
            note_b_hash="h4",
        )
        # The latest decision should be NO
        decisions = get_valid_decisions(
            engine=db_engine,
            current_hashes={"a.md": "h3", "b.md": "h4"},
        )
        assert (Path("a.md"), Path("b.md")) in decisions


class TestGetValidDecisions:
    """Tests for retrieving valid (non-stale) decisions."""

    def test_returns_empty_when_no_decisions(self, db_engine) -> None:
        decisions = get_valid_decisions(
            engine=db_engine,
            current_hashes={"a.md": "h1"},
        )
        assert decisions == set()

    def test_excludes_stale_decision_when_note_a_changed(self, db_engine) -> None:
        save_decision(
            engine=db_engine,
            note_a_path="a.md",
            note_b_path="b.md",
            decision="YES",
            note_a_hash="old_hash",
            note_b_hash="hash_b",
        )
        decisions = get_valid_decisions(
            engine=db_engine,
            current_hashes={"a.md": "new_hash", "b.md": "hash_b"},
        )
        assert len(decisions) == 0

    def test_excludes_stale_decision_when_note_b_changed(self, db_engine) -> None:
        save_decision(
            engine=db_engine,
            note_a_path="a.md",
            note_b_path="b.md",
            decision="NO",
            note_a_hash="hash_a",
            note_b_hash="old_hash",
        )
        decisions = get_valid_decisions(
            engine=db_engine,
            current_hashes={"a.md": "hash_a", "b.md": "new_hash"},
        )
        assert len(decisions) == 0

    def test_valid_decision_returned(self, db_engine) -> None:
        save_decision(
            engine=db_engine,
            note_a_path="a.md",
            note_b_path="b.md",
            decision="YES",
            note_a_hash="h1",
            note_b_hash="h2",
        )
        decisions = get_valid_decisions(
            engine=db_engine,
            current_hashes={"a.md": "h1", "b.md": "h2"},
        )
        assert (Path("a.md"), Path("b.md")) in decisions

    def test_excludes_decision_when_note_missing_from_vault(self, db_engine) -> None:
        """Decisions for notes no longer in vault are excluded."""
        save_decision(
            engine=db_engine,
            note_a_path="a.md",
            note_b_path="b.md",
            decision="YES",
            note_a_hash="h1",
            note_b_hash="h2",
        )
        # Note b.md is no longer in the vault
        decisions = get_valid_decisions(
            engine=db_engine,
            current_hashes={"a.md": "h1"},
        )
        assert len(decisions) == 0

    def test_multiple_valid_and_invalid(self, db_engine) -> None:
        save_decision(
            engine=db_engine,
            note_a_path="a.md",
            note_b_path="b.md",
            decision="YES",
            note_a_hash="h1",
            note_b_hash="h2",
        )
        save_decision(
            engine=db_engine,
            note_a_path="c.md",
            note_b_path="d.md",
            decision="NO",
            note_a_hash="h3",
            note_b_hash="old_h4",
        )
        decisions = get_valid_decisions(
            engine=db_engine,
            current_hashes={
                "a.md": "h1",
                "b.md": "h2",
                "c.md": "h3",
                "d.md": "new_h4",
            },
        )
        assert (Path("a.md"), Path("b.md")) in decisions
        assert (Path("c.md"), Path("d.md")) not in decisions
