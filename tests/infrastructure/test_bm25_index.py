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


class TestBM25IndexQuery:
    """Tests for the BM25Index.query() method."""

    def test_query_returns_results(self) -> None:
        texts = ["the cat sat on the mat", "the dog played in the park"]
        index = BM25Index(texts)
        results = index.query(query_text="cat mat", top_k=2)
        assert len(results) == 2

    def test_query_returns_tuples_of_index_and_score(self) -> None:
        texts = ["alpha beta", "gamma delta"]
        index = BM25Index(texts)
        results = index.query(query_text="alpha", top_k=2)
        for doc_idx, score in results:
            assert isinstance(doc_idx, int)
            assert isinstance(score, float)

    def test_query_ranks_relevant_doc_first(self) -> None:
        texts = [
            "machine learning neural networks",
            "cooking recipes italian pasta",
            "deep learning artificial intelligence",
        ]
        index = BM25Index(texts)
        results = index.query(query_text="machine learning", top_k=3)
        # Document 0 should be ranked highest (most relevant)
        assert results[0][0] == 0, "Most relevant doc should be first"

    def test_query_scores_are_non_negative(self) -> None:
        texts = ["hello world", "foo bar", "hello foo"]
        index = BM25Index(texts)
        results = index.query(query_text="hello", top_k=3)
        for _, score in results:
            assert score >= 0.0, f"BM25 scores should be non-negative, got {score}"

    def test_query_top_k_limits_results(self) -> None:
        texts = ["doc one", "doc two", "doc three", "doc four"]
        index = BM25Index(texts)
        results = index.query(query_text="doc", top_k=2)
        assert len(results) == 2

    def test_query_top_k_larger_than_corpus(self) -> None:
        """top_k larger than corpus returns all documents."""
        texts = ["alpha", "beta"]
        index = BM25Index(texts)
        results = index.query(query_text="alpha", top_k=10)
        assert len(results) == 2

    def test_query_returns_sorted_by_score_descending(self) -> None:
        texts = ["cat dog", "cat", "fish bird"]
        index = BM25Index(texts)
        results = index.query(query_text="cat dog", top_k=3)
        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True), "Results should be sorted by score descending"

    def test_query_all_scores_returns_all_documents(self) -> None:
        texts = ["one two three", "four five six", "seven eight nine"]
        index = BM25Index(texts)
        results = index.query_all_scores(query_text="one two")
        assert len(results) == 3, "Should return a score for every document"

    def test_query_all_scores_relevant_doc_scores_highest(self) -> None:
        texts = [
            "machine learning algorithms",
            "cooking pasta recipes",
            "deep learning neural networks",
        ]
        index = BM25Index(texts)
        scores = index.query_all_scores(query_text="machine learning")
        assert scores[0] > scores[1], "Relevant doc should score higher"
