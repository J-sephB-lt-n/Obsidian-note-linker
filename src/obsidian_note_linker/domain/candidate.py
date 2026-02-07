"""Candidate pair domain model.

A CandidatePair represents two notes identified as potentially related
by the hybrid similarity algorithm (semantic + lexical via RRF).
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CandidatePair:
    """Two notes identified as potentially related.

    Stores both per-direction scores (A→B and B→A) and the combined
    RRF score used for final ranking.

    Attributes:
        note_a_path: Relative path of the first note.
        note_b_path: Relative path of the second note.
        semantic_similarity: Cosine similarity between embeddings (symmetric).
        semantic_rank_a_to_b: Rank of B in A's semantic ranking (1-based).
        semantic_rank_b_to_a: Rank of A in B's semantic ranking (1-based).
        lexical_score_a_to_b: BM25 score when A queries for B.
        lexical_score_b_to_a: BM25 score when B queries for A.
        lexical_rank_a_to_b: Rank of B in A's BM25 ranking (1-based).
        lexical_rank_b_to_a: Rank of A in B's BM25 ranking (1-based).
        rrf_score: Combined Reciprocal Rank Fusion score (higher = more related).
    """

    note_a_path: Path
    note_b_path: Path
    semantic_similarity: float
    semantic_rank_a_to_b: int
    semantic_rank_b_to_a: int
    lexical_score_a_to_b: float
    lexical_score_b_to_a: float
    lexical_rank_a_to_b: int
    lexical_rank_b_to_a: int
    rrf_score: float

    @property
    def pair_key(self) -> tuple[Path, Path]:
        """Return a canonical sorted key for this pair.

        The key is deterministic regardless of which note is A vs B,
        enabling deduplication and set-based lookups.
        """
        return tuple(sorted([self.note_a_path, self.note_b_path]))  # type: ignore[return-value]

    @property
    def explanation(self) -> str:
        """Human-readable explanation of why this pair was suggested.

        Includes semantic similarity, best BM25 score, and combined
        RRF score.
        """
        best_bm25 = max(self.lexical_score_a_to_b, self.lexical_score_b_to_a)
        return (
            f"Semantic similarity: {self.semantic_similarity:.2f} | "
            f"BM25 score: {best_bm25:.1f} | "
            f"RRF score: {self.rrf_score:.4f}"
        )
