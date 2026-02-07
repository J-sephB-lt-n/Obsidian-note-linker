"""Reciprocal Rank Fusion (RRF) ranking functions.

Provides the RRF formula for combining semantic and lexical rankings,
and a utility for converting raw scores into 1-based ranks.
"""

RRF_K = 60
"""Standard RRF constant.  Controls how much weight lower-ranked
results receive.  Higher k compresses score differences."""


def compute_rrf_score(
    semantic_rank: int,
    lexical_rank: int,
    k: int = RRF_K,
) -> float:
    """Compute the Reciprocal Rank Fusion score for a single document.

    Formula: ``RRF(d) = 1/(k + semantic_rank) + 1/(k + lexical_rank)``

    Args:
        semantic_rank: 1-based rank from semantic (cosine) similarity.
        lexical_rank: 1-based rank from lexical (BM25) similarity.
        k: RRF smoothing constant (default 60).

    Returns:
        Combined RRF score (higher = more relevant).

    Raises:
        ValueError: If either rank is not a positive integer.
    """
    if semantic_rank < 1:
        raise ValueError(f"semantic_rank must be positive, got {semantic_rank}")
    if lexical_rank < 1:
        raise ValueError(f"lexical_rank must be positive, got {lexical_rank}")

    return 1.0 / (k + semantic_rank) + 1.0 / (k + lexical_rank)


def ranks_from_scores(scores: list[float]) -> list[int]:
    """Convert a list of scores to 1-based dense ranks (highest score = rank 1).

    Tied scores receive the same rank.

    Args:
        scores: Raw scores (higher is better).

    Returns:
        List of 1-based ranks, same length as input.
    """
    if not scores:
        return []

    # Sort indices by score descending
    sorted_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

    ranks = [0] * len(scores)
    current_rank = 1

    for pos, idx in enumerate(sorted_indices):
        if pos > 0 and scores[idx] < scores[sorted_indices[pos - 1]]:
            current_rank = pos + 1
        ranks[idx] = current_rank

    return ranks
