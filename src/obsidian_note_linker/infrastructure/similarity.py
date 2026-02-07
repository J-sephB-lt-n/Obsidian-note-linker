"""Cosine similarity computation using numpy.

Provides efficient pairwise cosine similarity for embedding vectors,
used during candidate generation to rank notes by semantic similarity.
"""

import numpy as np


def compute_pairwise_cosine_similarity(
    embeddings: list[list[float]],
) -> list[list[float]]:
    """Compute the pairwise cosine similarity matrix for a set of embeddings.

    Uses numpy for efficient vectorised computation.

    Args:
        embeddings: List of embedding vectors (each a list of floats).
                    All vectors must have the same dimensionality.

    Returns:
        N×N matrix where ``matrix[i][j]`` is the cosine similarity
        between embeddings ``i`` and ``j``.  Values range from -1 to 1.
        Diagonal values are 1.0 (self-similarity).

    Raises:
        ValueError: If the embeddings list is empty.
    """
    if not embeddings:
        raise ValueError("compute_pairwise_cosine_similarity requires at least one embedding")

    matrix = np.array(embeddings, dtype=np.float64)

    # Normalise each row to unit length
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-10)  # Avoid division by zero
    normalised = matrix / norms

    # Cosine similarity = dot product of normalised vectors
    similarity = (normalised @ normalised.T).tolist()

    return similarity
