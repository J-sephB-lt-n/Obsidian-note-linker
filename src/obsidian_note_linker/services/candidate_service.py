"""Candidate generation service — orchestrates hybrid similarity ranking.

Combines semantic (cosine similarity) and lexical (BM25) rankings using
Reciprocal Rank Fusion (RRF) to identify candidate note pairs for
human review.  Filters out already-linked and previously-decided pairs.
"""

import logging
from pathlib import Path

from sqlalchemy.engine import Engine

from obsidian_note_linker.domain.candidate import CandidatePair
from obsidian_note_linker.domain.markdown_stripper import prepare_note_for_embedding
from obsidian_note_linker.domain.ranking import compute_rrf_score, ranks_from_scores
from obsidian_note_linker.domain.related_section_parser import get_existing_link_pairs
from obsidian_note_linker.infrastructure.bm25_index import BM25Index
from obsidian_note_linker.infrastructure.decision_store import get_valid_decisions
from obsidian_note_linker.infrastructure.embedding_store import get_all_embeddings
from obsidian_note_linker.infrastructure.note_store import get_all_note_records
from obsidian_note_linker.infrastructure.similarity import (
    compute_pairwise_cosine_similarity,
)
from obsidian_note_linker.infrastructure.vault_scanner import scan_vault

logger = logging.getLogger(__name__)


class CandidateService:
    """Orchestrates candidate pair generation using hybrid similarity.

    Loads embeddings, builds a BM25 index, computes pairwise rankings,
    applies RRF, and filters out already-linked and decided pairs.

    Args:
        engine: SQLAlchemy engine for database access.
        vault_path: Absolute path to the Obsidian vault.
    """

    def __init__(self, engine: Engine, vault_path: Path) -> None:
        self._engine = engine
        self._vault_path = vault_path
        self._candidates: list[CandidatePair] | None = None

    def generate_candidates(self) -> list[CandidatePair]:
        """Generate ranked candidate pairs using hybrid similarity.

        Steps:
            1. Load all indexed notes and their embeddings.
            2. Prepare texts and build BM25 index.
            3. Compute pairwise semantic and lexical scores.
            4. Combine rankings using RRF.
            5. Filter out bidirectionally-linked pairs.
            6. Filter out valid prior decisions (YES/NO).
            7. Sort by RRF score descending.

        Returns:
            List of candidate pairs sorted by RRF score (highest first).
        """
        # 1. Load indexed notes and embeddings
        note_records = get_all_note_records(self._engine)
        if len(note_records) < 2:
            logger.info("Fewer than 2 indexed notes — no candidates to generate")
            self._candidates = []
            return self._candidates

        all_embeddings = get_all_embeddings(self._engine)

        # Build ordered lists: paths, hashes, embeddings
        paths: list[str] = []
        hashes: list[str] = []
        embeddings: list[list[float]] = []

        for record in note_records:
            emb = all_embeddings.get(record.content_hash)
            if emb is not None:
                paths.append(record.relative_path)
                hashes.append(record.content_hash)
                embeddings.append(emb)

        n = len(paths)
        if n < 2:
            logger.info("Fewer than 2 notes with embeddings — no candidates")
            self._candidates = []
            return self._candidates

        logger.info("Generating candidates for %d notes", n)

        # 2. Prepare texts for BM25 and build index
        vault_notes = scan_vault(self._vault_path)
        note_content_by_path: dict[str, str] = {
            str(note.relative_path): note.content for note in vault_notes
        }

        bm25_texts = [
            prepare_note_for_embedding(
                title=Path(p).stem,
                content=note_content_by_path.get(p, ""),
            )
            for p in paths
        ]
        bm25_index = BM25Index(bm25_texts)

        # 3. Compute pairwise scores
        semantic_matrix = compute_pairwise_cosine_similarity(embeddings)
        lexical_matrix = bm25_index.get_pairwise_scores()

        # 4. Compute per-note rankings and RRF scores for all pairs
        candidates = _compute_rrf_candidates(
            paths=paths,
            semantic_matrix=semantic_matrix,
            lexical_matrix=lexical_matrix,
        )

        # 5. Filter out bidirectionally-linked pairs
        notes_by_path: dict[Path, str] = {
            Path(p): note_content_by_path.get(p, "") for p in paths
        }
        linked_pairs = get_existing_link_pairs(notes_by_path)
        before_link_filter = len(candidates)
        candidates = [
            c for c in candidates if c.pair_key not in linked_pairs
        ]
        link_filtered = before_link_filter - len(candidates)

        # 6. Filter out valid prior decisions
        current_hashes = dict(zip(paths, hashes))
        decided_pairs = get_valid_decisions(
            engine=self._engine, current_hashes=current_hashes,
        )
        before_decision_filter = len(candidates)
        candidates = [
            c for c in candidates if c.pair_key not in decided_pairs
        ]
        decision_filtered = before_decision_filter - len(candidates)

        # 7. Sort by RRF score descending
        candidates.sort(key=lambda c: c.rrf_score, reverse=True)

        logger.info(
            "Candidate generation complete: %d candidates "
            "(%d filtered by links, %d filtered by decisions)",
            len(candidates), link_filtered, decision_filtered,
        )

        self._candidates = candidates
        return self._candidates

    def get_candidate_count(self) -> int:
        """Return the number of candidates from the last generation.

        If ``generate_candidates`` has not been called yet, calls it.

        Returns:
            Number of candidate pairs.
        """
        if self._candidates is None:
            self.generate_candidates()
        assert self._candidates is not None, "generate_candidates should have set _candidates"
        return len(self._candidates)


def _compute_rrf_candidates(
    paths: list[str],
    semantic_matrix: list[list[float]],
    lexical_matrix: list[list[float]],
) -> list[CandidatePair]:
    """Compute RRF-scored candidate pairs from pairwise score matrices.

    For each unique pair (i, j), computes RRF from both directions
    (i→j and j→i) and takes the maximum as the pair's RRF score.

    Args:
        paths: Ordered list of note relative paths.
        semantic_matrix: N×N cosine similarity matrix.
        lexical_matrix: N×N BM25 score matrix.

    Returns:
        List of CandidatePair objects (unsorted).
    """
    n = len(paths)

    # Compute per-note rankings (excluding self)
    semantic_ranks = _compute_rank_matrix(semantic_matrix)
    lexical_ranks = _compute_rank_matrix(lexical_matrix)

    # Build candidate pairs (each unique pair only once)
    seen: set[tuple[str, str]] = set()
    candidates: list[CandidatePair] = []

    for i in range(n):
        for j in range(n):
            if i == j:
                continue

            pair_key = tuple(sorted([paths[i], paths[j]]))
            if pair_key in seen:
                continue
            seen.add(pair_key)  # type: ignore[arg-type]

            # Compute RRF from both directions, take maximum
            rrf_i_to_j = compute_rrf_score(
                semantic_rank=semantic_ranks[i][j],
                lexical_rank=lexical_ranks[i][j],
            )
            rrf_j_to_i = compute_rrf_score(
                semantic_rank=semantic_ranks[j][i],
                lexical_rank=lexical_ranks[j][i],
            )
            rrf = max(rrf_i_to_j, rrf_j_to_i)

            candidates.append(CandidatePair(
                note_a_path=Path(paths[i]),
                note_b_path=Path(paths[j]),
                semantic_similarity=semantic_matrix[i][j],
                semantic_rank_a_to_b=semantic_ranks[i][j],
                semantic_rank_b_to_a=semantic_ranks[j][i],
                lexical_score_a_to_b=lexical_matrix[i][j],
                lexical_score_b_to_a=lexical_matrix[j][i],
                lexical_rank_a_to_b=lexical_ranks[i][j],
                lexical_rank_b_to_a=lexical_ranks[j][i],
                rrf_score=rrf,
            ))

    return candidates


def _compute_rank_matrix(score_matrix: list[list[float]]) -> list[list[int]]:
    """Convert an N×N score matrix into an N×N rank matrix.

    For each row, ranks are computed among non-self entries (1-based,
    highest score = rank 1).  The diagonal (self-rank) is set to 0.

    Args:
        score_matrix: N×N matrix of scores.

    Returns:
        N×N matrix of 1-based ranks (0 on diagonal).
    """
    n = len(score_matrix)
    rank_matrix: list[list[int]] = [[0] * n for _ in range(n)]

    for i in range(n):
        # Get scores for all other notes (excluding self)
        other_indices = [j for j in range(n) if j != i]
        other_scores = [score_matrix[i][j] for j in other_indices]

        ranks = ranks_from_scores(other_scores)

        for pos, j in enumerate(other_indices):
            rank_matrix[i][j] = ranks[pos]

    return rank_matrix
