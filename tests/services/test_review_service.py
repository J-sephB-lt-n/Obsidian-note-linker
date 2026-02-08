"""Tests for the review service."""

from pathlib import Path

from sqlalchemy.engine import Engine

from obsidian_note_linker.domain.candidate import CandidatePair
from obsidian_note_linker.domain.note import compute_content_hash
from obsidian_note_linker.infrastructure.note_store import upsert_note_record
from obsidian_note_linker.services.review_service import ReviewService


def _make_candidate(
    note_a: str,
    note_b: str,
    rrf_score: float = 0.03,
) -> CandidatePair:
    """Create a CandidatePair with minimal required fields for testing."""
    return CandidatePair(
        note_a_path=Path(note_a),
        note_b_path=Path(note_b),
        semantic_similarity=0.8,
        semantic_rank_a_to_b=1,
        semantic_rank_b_to_a=1,
        lexical_score_a_to_b=5.0,
        lexical_score_b_to_a=4.0,
        lexical_rank_a_to_b=1,
        lexical_rank_b_to_a=1,
        rrf_score=rrf_score,
    )


def _setup_vault_notes(
    vault_path: Path,
    db_engine: Engine,
    notes: dict[str, str],
) -> None:
    """Create note files on disk and upsert note records in DB."""
    for rel_path, content in notes.items():
        full_path = vault_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        upsert_note_record(
            engine=db_engine,
            relative_path=rel_path,
            content_hash=compute_content_hash(content),
        )


class TestGetTargetsWithCandidates:
    """Tests for ReviewService.get_targets_with_candidates()."""

    def test_returns_targets_with_counts(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        candidates = [
            _make_candidate("a.md", "b.md", rrf_score=0.05),
            _make_candidate("a.md", "c.md", rrf_score=0.03),
            _make_candidate("b.md", "c.md", rrf_score=0.02),
        ]
        service = ReviewService(engine=db_engine, vault_path=vault_path)
        targets = service.get_targets_with_candidates(candidates)

        # All three notes appear as targets
        target_paths = {t.note_path for t in targets}
        assert target_paths == {Path("a.md"), Path("b.md"), Path("c.md")}

    def test_candidate_counts_are_correct(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        candidates = [
            _make_candidate("a.md", "b.md"),
            _make_candidate("a.md", "c.md"),
            _make_candidate("b.md", "c.md"),
        ]
        service = ReviewService(engine=db_engine, vault_path=vault_path)
        targets = service.get_targets_with_candidates(candidates)

        counts = {t.note_path: t.candidate_count for t in targets}
        assert counts[Path("a.md")] == 2  # paired with b and c
        assert counts[Path("b.md")] == 2  # paired with a and c
        assert counts[Path("c.md")] == 2  # paired with a and b

    def test_returns_empty_for_no_candidates(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        service = ReviewService(engine=db_engine, vault_path=vault_path)
        targets = service.get_targets_with_candidates([])

        assert targets == []

    def test_targets_sorted_alphabetically(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        candidates = [
            _make_candidate("c.md", "a.md"),
            _make_candidate("b.md", "a.md"),
        ]
        service = ReviewService(engine=db_engine, vault_path=vault_path)
        targets = service.get_targets_with_candidates(candidates)

        paths = [t.note_path for t in targets]
        assert paths == sorted(paths)

    def test_title_derived_from_filename(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        candidates = [_make_candidate("My Cool Note.md", "other.md")]
        service = ReviewService(engine=db_engine, vault_path=vault_path)
        targets = service.get_targets_with_candidates(candidates)

        titles = {t.note_path: t.title for t in targets}
        assert titles[Path("My Cool Note.md")] == "My Cool Note"

    def test_title_for_nested_note(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        candidates = [_make_candidate("folder/sub/note.md", "other.md")]
        service = ReviewService(engine=db_engine, vault_path=vault_path)
        targets = service.get_targets_with_candidates(candidates)

        titles = {t.note_path: t.title for t in targets}
        assert titles[Path("folder/sub/note.md")] == "note"


class TestGetCandidatesForTarget:
    """Tests for ReviewService.get_candidates_for_target()."""

    def test_returns_candidates_involving_target(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        candidates = [
            _make_candidate("a.md", "b.md"),
            _make_candidate("a.md", "c.md"),
            _make_candidate("b.md", "c.md"),
        ]
        service = ReviewService(engine=db_engine, vault_path=vault_path)
        result = service.get_candidates_for_target(
            candidates=candidates, target=Path("a.md"),
        )

        assert len(result) == 2
        for c in result:
            assert Path("a.md") in (c.note_a_path, c.note_b_path)

    def test_sorted_by_rrf_score_descending(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        candidates = [
            _make_candidate("a.md", "b.md", rrf_score=0.02),
            _make_candidate("a.md", "c.md", rrf_score=0.05),
        ]
        service = ReviewService(engine=db_engine, vault_path=vault_path)
        result = service.get_candidates_for_target(
            candidates=candidates, target=Path("a.md"),
        )

        assert len(result) == 2
        assert result[0].rrf_score >= result[1].rrf_score

    def test_excludes_skipped_pairs(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        candidates = [
            _make_candidate("a.md", "b.md"),
            _make_candidate("a.md", "c.md"),
        ]
        skipped = {(Path("a.md"), Path("b.md"))}
        service = ReviewService(engine=db_engine, vault_path=vault_path)
        result = service.get_candidates_for_target(
            candidates=candidates,
            target=Path("a.md"),
            skipped_pair_keys=skipped,
        )

        assert len(result) == 1
        assert Path("b.md") not in (result[0].note_a_path, result[0].note_b_path)

    def test_returns_empty_when_no_candidates_for_target(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        candidates = [_make_candidate("b.md", "c.md")]
        service = ReviewService(engine=db_engine, vault_path=vault_path)
        result = service.get_candidates_for_target(
            candidates=candidates, target=Path("a.md"),
        )

        assert result == []

    def test_returns_empty_when_all_skipped(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        candidates = [_make_candidate("a.md", "b.md")]
        skipped = {(Path("a.md"), Path("b.md"))}
        service = ReviewService(engine=db_engine, vault_path=vault_path)
        result = service.get_candidates_for_target(
            candidates=candidates,
            target=Path("a.md"),
            skipped_pair_keys=skipped,
        )

        assert result == []


class TestRecordDecision:
    """Tests for ReviewService.record_decision()."""

    def test_saves_yes_decision(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        notes = {"a.md": "# A\n\nContent A", "b.md": "# B\n\nContent B"}
        _setup_vault_notes(vault_path, db_engine, notes)

        service = ReviewService(engine=db_engine, vault_path=vault_path)
        service.record_decision(
            note_a_path=Path("a.md"),
            note_b_path=Path("b.md"),
            decision="YES",
        )

        # Verify decision was saved to DB
        from obsidian_note_linker.infrastructure.decision_store import (
            get_valid_decisions,
        )

        current_hashes = {
            p: compute_content_hash(c) for p, c in notes.items()
        }
        valid = get_valid_decisions(
            engine=db_engine, current_hashes=current_hashes,
        )
        assert (Path("a.md"), Path("b.md")) in valid

    def test_saves_no_decision(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        notes = {"a.md": "# A\n\nContent A", "b.md": "# B\n\nContent B"}
        _setup_vault_notes(vault_path, db_engine, notes)

        service = ReviewService(engine=db_engine, vault_path=vault_path)
        service.record_decision(
            note_a_path=Path("a.md"),
            note_b_path=Path("b.md"),
            decision="NO",
        )

        from obsidian_note_linker.infrastructure.decision_store import (
            get_valid_decisions,
        )

        current_hashes = {
            p: compute_content_hash(c) for p, c in notes.items()
        }
        valid = get_valid_decisions(
            engine=db_engine, current_hashes=current_hashes,
        )
        assert (Path("a.md"), Path("b.md")) in valid

    def test_raises_for_invalid_decision(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        notes = {"a.md": "# A\n\nContent A", "b.md": "# B\n\nContent B"}
        _setup_vault_notes(vault_path, db_engine, notes)

        service = ReviewService(engine=db_engine, vault_path=vault_path)

        import pytest

        with pytest.raises(AssertionError):
            service.record_decision(
                note_a_path=Path("a.md"),
                note_b_path=Path("b.md"),
                decision="SKIP",
            )

    def test_raises_for_missing_note_record(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        """Decision requires both notes to have indexed records."""
        service = ReviewService(engine=db_engine, vault_path=vault_path)

        import pytest

        with pytest.raises(ValueError, match="No indexed record"):
            service.record_decision(
                note_a_path=Path("nonexistent.md"),
                note_b_path=Path("also_missing.md"),
                decision="YES",
            )


class TestReadAndRenderNote:
    """Tests for ReviewService.read_and_render_note()."""

    def test_returns_title_and_html(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        (vault_path / "test.md").write_text("# My Note\n\nSome content.")
        service = ReviewService(engine=db_engine, vault_path=vault_path)

        title, html = service.read_and_render_note(note_path=Path("test.md"))

        assert title == "test"
        assert "<p>" in html
        assert "Some content" in html

    def test_renders_markdown_to_html(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        (vault_path / "note.md").write_text("**bold** text")
        service = ReviewService(engine=db_engine, vault_path=vault_path)

        _, html = service.read_and_render_note(note_path=Path("note.md"))

        assert "<strong>bold</strong>" in html

    def test_nested_note_path(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        sub = vault_path / "folder"
        sub.mkdir()
        (sub / "deep.md").write_text("# Deep\n\nNested note.")
        service = ReviewService(engine=db_engine, vault_path=vault_path)

        title, html = service.read_and_render_note(
            note_path=Path("folder/deep.md"),
        )

        assert title == "deep"
        assert "Nested note" in html

    def test_raises_for_missing_file(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        service = ReviewService(engine=db_engine, vault_path=vault_path)

        import pytest

        with pytest.raises(FileNotFoundError):
            service.read_and_render_note(note_path=Path("missing.md"))


class TestGetRandomTarget:
    """Tests for ReviewService.get_random_target()."""

    def test_returns_a_valid_target_path(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        candidates = [
            _make_candidate("a.md", "b.md"),
            _make_candidate("a.md", "c.md"),
        ]
        service = ReviewService(engine=db_engine, vault_path=vault_path)
        target = service.get_random_target(candidates)

        assert target is not None
        all_paths = {Path("a.md"), Path("b.md"), Path("c.md")}
        assert target in all_paths

    def test_returns_none_for_empty_candidates(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        service = ReviewService(engine=db_engine, vault_path=vault_path)
        target = service.get_random_target([])

        assert target is None

    def test_returns_different_targets_over_many_calls(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        """Randomness test — with 3 targets, not all 30 calls should be same."""
        candidates = [
            _make_candidate("a.md", "b.md"),
            _make_candidate("b.md", "c.md"),
            _make_candidate("a.md", "c.md"),
        ]
        service = ReviewService(engine=db_engine, vault_path=vault_path)
        results = {service.get_random_target(candidates) for _ in range(30)}

        assert len(results) > 1, "Random target should vary across calls"
