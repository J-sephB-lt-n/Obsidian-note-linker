"""Tests for RRF ranking functions."""

import pytest

from obsidian_note_linker.domain.ranking import (
    RRF_K,
    compute_rrf_score,
    ranks_from_scores,
)


class TestComputeRrfScore:
    """Tests for the RRF score computation."""

    def test_best_possible_score(self) -> None:
        """Rank 1 in both yields the maximum RRF score."""
        score = compute_rrf_score(semantic_rank=1, lexical_rank=1)
        expected = 2.0 / (RRF_K + 1)
        assert score == pytest.approx(expected)

    def test_worst_ranks_give_lower_score(self) -> None:
        best = compute_rrf_score(semantic_rank=1, lexical_rank=1)
        worst = compute_rrf_score(semantic_rank=100, lexical_rank=100)
        assert worst < best

    def test_formula_matches_rrf_definition(self) -> None:
        """RRF(d) = 1/(k + semantic_rank) + 1/(k + lexical_rank)."""
        score = compute_rrf_score(semantic_rank=5, lexical_rank=10)
        expected = 1.0 / (RRF_K + 5) + 1.0 / (RRF_K + 10)
        assert score == pytest.approx(expected)

    def test_symmetric_in_rank_swapping(self) -> None:
        """RRF(sem=3, lex=7) == RRF(sem=7, lex=3)."""
        score_a = compute_rrf_score(semantic_rank=3, lexical_rank=7)
        score_b = compute_rrf_score(semantic_rank=7, lexical_rank=3)
        assert score_a == pytest.approx(score_b)

    def test_custom_k(self) -> None:
        score = compute_rrf_score(semantic_rank=1, lexical_rank=1, k=10)
        assert score == pytest.approx(2.0 / 11)

    def test_rank_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            compute_rrf_score(semantic_rank=0, lexical_rank=1)

        with pytest.raises(ValueError, match="positive"):
            compute_rrf_score(semantic_rank=1, lexical_rank=0)


class TestRanksFromScores:
    """Tests for converting scores to 1-based ranks."""

    def test_descending_order(self) -> None:
        scores = [0.9, 0.5, 0.8, 0.1]
        ranks = ranks_from_scores(scores)
        # 0.9→rank1, 0.8→rank2, 0.5→rank3, 0.1→rank4
        assert ranks == [1, 3, 2, 4]

    def test_single_element(self) -> None:
        assert ranks_from_scores([42.0]) == [1]

    def test_tied_scores_get_same_rank(self) -> None:
        scores = [0.5, 0.9, 0.5]
        ranks = ranks_from_scores(scores)
        # 0.9→rank1, both 0.5→rank2
        assert ranks[1] == 1
        assert ranks[0] == ranks[2]
        assert ranks[0] == 2

    def test_empty_list(self) -> None:
        assert ranks_from_scores([]) == []
