"""Tests for cosine similarity computation."""

import pytest

from obsidian_note_linker.infrastructure.similarity import (
    compute_pairwise_cosine_similarity,
)


class TestComputePairwiseCosineSimilarity:
    """Tests for the pairwise cosine similarity matrix computation."""

    def test_identical_vectors_have_similarity_one(self) -> None:
        embeddings = [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
        matrix = compute_pairwise_cosine_similarity(embeddings)
        assert matrix[0][1] == pytest.approx(1.0, abs=1e-6)
        assert matrix[1][0] == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors_have_similarity_zero(self) -> None:
        embeddings = [[1.0, 0.0], [0.0, 1.0]]
        matrix = compute_pairwise_cosine_similarity(embeddings)
        assert matrix[0][1] == pytest.approx(0.0, abs=1e-6)

    def test_diagonal_is_one(self) -> None:
        embeddings = [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]]
        matrix = compute_pairwise_cosine_similarity(embeddings)
        for i in range(3):
            assert matrix[i][i] == pytest.approx(1.0, abs=1e-6)

    def test_matrix_is_symmetric(self) -> None:
        embeddings = [[1.0, 2.0], [3.0, 1.0], [0.5, 0.5]]
        matrix = compute_pairwise_cosine_similarity(embeddings)
        for i in range(3):
            for j in range(3):
                assert matrix[i][j] == pytest.approx(matrix[j][i], abs=1e-6)

    def test_matrix_shape(self) -> None:
        embeddings = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
        matrix = compute_pairwise_cosine_similarity(embeddings)
        assert len(matrix) == 3
        assert all(len(row) == 3 for row in matrix)

    def test_known_similarity(self) -> None:
        """Verify against manually computed cosine similarity."""
        a = [3.0, 4.0]
        b = [4.0, 3.0]
        # cos(a, b) = (12 + 12) / (5 * 5) = 24/25 = 0.96
        embeddings = [a, b]
        matrix = compute_pairwise_cosine_similarity(embeddings)
        assert matrix[0][1] == pytest.approx(0.96, abs=1e-6)

    def test_single_vector(self) -> None:
        matrix = compute_pairwise_cosine_similarity([[1.0, 2.0]])
        assert matrix == [[pytest.approx(1.0, abs=1e-6)]]

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            compute_pairwise_cosine_similarity([])

    def test_values_in_valid_range(self) -> None:
        """All similarity values should be between -1 and 1."""
        embeddings = [[1.0, -2.0, 3.0], [-1.0, 2.0, -3.0], [0.5, 0.5, 0.5]]
        matrix = compute_pairwise_cosine_similarity(embeddings)
        for row in matrix:
            for val in row:
                assert -1.0 - 1e-6 <= val <= 1.0 + 1e-6
