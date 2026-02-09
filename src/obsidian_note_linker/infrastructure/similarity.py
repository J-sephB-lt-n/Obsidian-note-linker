"""Cosine similarity computation using numpy.

Provides efficient pairwise cosine similarity for embedding vectors
and single-query similarity for document search.  Used during
candidate generation and search to rank notes by semantic similarity.
"""

import logging
import time

import numpy as np

logger = logging.getLogger(__name__)


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

    t0 = time.perf_counter()
    n = len(embeddings)
    matrix = np.array(embeddings, dtype=np.float64)

    # Normalise each row to unit length
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-10)  # Avoid division by zero
    normalised = matrix / norms

    # Cosine similarity = dot product of normalised vectors
    similarity = (normalised @ normalised.T).tolist()

    logger.debug(
        "Pairwise cosine similarity: %d×%d matrix (%.3fs)",
        n, n, time.perf_counter() - t0,
    )
    return similarity


def compute_query_cosine_similarity(
    query_embedding: list[float],
    corpus_embeddings: list[list[float]],
) -> list[float]:
    """Compute cosine similarity between a query and each corpus vector.

    Args:
        query_embedding: Single query embedding vector.
        corpus_embeddings: List of corpus embedding vectors.  All must
                          have the same dimensionality as the query.

    Returns:
        List of similarity scores in corpus order.  Values range
        from -1 to 1 (higher = more similar).

    Raises:
        ValueError: If the corpus is empty.
    """
    if not corpus_embeddings:
        raise ValueError(
            "compute_query_cosine_similarity requires at least one corpus embedding"
        )

    t0 = time.perf_counter()
    query = np.array(query_embedding, dtype=np.float64).reshape(1, -1)
    corpus = np.array(corpus_embeddings, dtype=np.float64)

    # Normalise query
    query_norm = np.linalg.norm(query)
    query_norm = max(query_norm, 1e-10)
    query_normed = query / query_norm

    # Normalise corpus
    corpus_norms = np.linalg.norm(corpus, axis=1, keepdims=True)
    corpus_norms = np.maximum(corpus_norms, 1e-10)
    corpus_normed = corpus / corpus_norms

    # Dot product gives cosine similarity
    similarities = (corpus_normed @ query_normed.T).flatten().tolist()

    logger.debug(
        "Query cosine similarity: 1×%d corpus (%.3fs)",
        len(corpus_embeddings), time.perf_counter() - t0,
    )
    return similarities
