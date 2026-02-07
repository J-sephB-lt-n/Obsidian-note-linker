"""Tests for candidate pair domain model."""

from pathlib import Path

from obsidian_note_linker.domain.candidate import CandidatePair


class TestCandidatePair:
    """Tests for the CandidatePair dataclass."""

    def test_creation_with_all_fields(self) -> None:
        pair = CandidatePair(
            note_a_path=Path("notes/alpha.md"),
            note_b_path=Path("notes/beta.md"),
            semantic_similarity=0.85,
            semantic_rank_a_to_b=3,
            semantic_rank_b_to_a=5,
            lexical_score_a_to_b=12.4,
            lexical_score_b_to_a=9.1,
            lexical_rank_a_to_b=7,
            lexical_rank_b_to_a=2,
            rrf_score=0.028,
        )
        assert pair.note_a_path == Path("notes/alpha.md")
        assert pair.note_b_path == Path("notes/beta.md")
        assert pair.semantic_similarity == 0.85
        assert pair.rrf_score == 0.028

    def test_is_frozen(self) -> None:
        pair = CandidatePair(
            note_a_path=Path("a.md"),
            note_b_path=Path("b.md"),
            semantic_similarity=0.5,
            semantic_rank_a_to_b=1,
            semantic_rank_b_to_a=1,
            lexical_score_a_to_b=1.0,
            lexical_score_b_to_a=1.0,
            lexical_rank_a_to_b=1,
            lexical_rank_b_to_a=1,
            rrf_score=0.03,
        )
        try:
            pair.rrf_score = 0.5  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass  # Expected — frozen dataclass

    def test_explanation_includes_all_scores(self) -> None:
        pair = CandidatePair(
            note_a_path=Path("a.md"),
            note_b_path=Path("b.md"),
            semantic_similarity=0.8123,
            semantic_rank_a_to_b=2,
            semantic_rank_b_to_a=4,
            lexical_score_a_to_b=15.3,
            lexical_score_b_to_a=11.7,
            lexical_rank_a_to_b=3,
            lexical_rank_b_to_a=6,
            rrf_score=0.029,
        )
        explanation = pair.explanation
        assert "0.81" in explanation, "Semantic similarity should be displayed"
        assert "RRF" in explanation or "rrf" in explanation.lower()
        assert "BM25" in explanation or "lexical" in explanation.lower()

    def test_pair_key_is_sorted_tuple(self) -> None:
        pair = CandidatePair(
            note_a_path=Path("z.md"),
            note_b_path=Path("a.md"),
            semantic_similarity=0.5,
            semantic_rank_a_to_b=1,
            semantic_rank_b_to_a=1,
            lexical_score_a_to_b=1.0,
            lexical_score_b_to_a=1.0,
            lexical_rank_a_to_b=1,
            lexical_rank_b_to_a=1,
            rrf_score=0.03,
        )
        assert pair.pair_key == (Path("a.md"), Path("z.md"))

    def test_pair_key_is_deterministic(self) -> None:
        """Same two notes always produce the same pair_key, regardless of order."""
        pair_1 = CandidatePair(
            note_a_path=Path("x.md"),
            note_b_path=Path("y.md"),
            semantic_similarity=0.5,
            semantic_rank_a_to_b=1,
            semantic_rank_b_to_a=1,
            lexical_score_a_to_b=1.0,
            lexical_score_b_to_a=1.0,
            lexical_rank_a_to_b=1,
            lexical_rank_b_to_a=1,
            rrf_score=0.03,
        )
        pair_2 = CandidatePair(
            note_a_path=Path("y.md"),
            note_b_path=Path("x.md"),
            semantic_similarity=0.5,
            semantic_rank_a_to_b=1,
            semantic_rank_b_to_a=1,
            lexical_score_a_to_b=1.0,
            lexical_score_b_to_a=1.0,
            lexical_rank_a_to_b=1,
            lexical_rank_b_to_a=1,
            rrf_score=0.03,
        )
        assert pair_1.pair_key == pair_2.pair_key
