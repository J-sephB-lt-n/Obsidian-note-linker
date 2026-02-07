"""Tests for BM25 index wrapper."""

import pytest

from obsidian_note_linker.infrastructure.bm25_index import BM25Index


class TestBM25Index:
    """Tests for the BM25Index wrapper."""

    def test_build_from_texts(self) -> None:
        texts = ["the cat sat on the mat", "the dog played in the park"]
        index = BM25Index(texts)
        assert index.num_documents == 2

    def test_pairwise_scores_shape(self) -> None:
        texts = ["alpha beta gamma", "beta gamma delta", "epsilon zeta"]
        index = BM25Index(texts)
        scores = index.get_pairwise_scores()
        assert len(scores) == 3
        assert all(len(row) == 3 for row in scores)

    def test_self_scores_are_zero(self) -> None:
        """Diagonal of the pairwise score matrix should be zero."""
        texts = ["word one two", "word three four", "word five six"]
        index = BM25Index(texts)
        scores = index.get_pairwise_scores()
        for i in range(len(texts)):
            assert scores[i][i] == 0.0, f"Self-score at [{i}][{i}] should be 0"

    def test_similar_documents_score_higher(self) -> None:
        texts = [
            "machine learning neural networks deep learning",
            "neural networks and deep learning models",
            "cooking recipes for italian pasta dishes",
        ]
        index = BM25Index(texts)
        scores = index.get_pairwise_scores()
        # Documents 0 and 1 share many terms; document 2 is unrelated
        assert scores[0][1] > scores[0][2], "Related docs should score higher"
        assert scores[1][0] > scores[1][2], "Related docs should score higher"

    def test_scores_are_non_negative(self) -> None:
        texts = ["hello world", "foo bar baz", "hello foo"]
        index = BM25Index(texts)
        scores = index.get_pairwise_scores()
        for row in scores:
            for s in row:
                assert s >= 0.0, f"BM25 scores should be non-negative, got {s}"

    def test_single_document(self) -> None:
        """Single document produces a 1×1 matrix with zero self-score."""
        index = BM25Index(["only one document here"])
        scores = index.get_pairwise_scores()
        assert scores == [[0.0]]

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            BM25Index([])
