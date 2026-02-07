"""BM25 lexical index wrapper using bm25s.

Provides an in-memory BM25 index for computing pairwise lexical
similarity scores between notes.  The index is rebuilt each time
indexing is triggered (not persisted to disk).
"""

import logging

import bm25s

logger = logging.getLogger(__name__)


class BM25Index:
    """In-memory BM25 index over a collection of text documents.

    Wraps the ``bm25s`` library to provide pairwise lexical similarity
    scoring for candidate generation.

    Args:
        texts: List of plain-text documents to index.

    Raises:
        ValueError: If the text list is empty.
    """

    def __init__(self, texts: list[str]) -> None:
        if not texts:
            raise ValueError("BM25Index requires at least one document")

        self._num_documents = len(texts)
        self._retriever = bm25s.BM25()
        self._tokens = bm25s.tokenize(texts, show_progress=False)
        self._retriever.index(self._tokens, show_progress=False)
        logger.info("Built BM25 index over %d documents", self._num_documents)

    @property
    def num_documents(self) -> int:
        """Return the number of indexed documents."""
        return self._num_documents

    def get_pairwise_scores(self) -> list[list[float]]:
        """Compute pairwise BM25 scores for all documents.

        Uses each document as a query against the full index.  Self-match
        scores (diagonal) are zeroed out.

        Returns:
            N×N matrix of BM25 scores, where ``scores[i][j]`` is the BM25
            score of document ``j`` when document ``i`` is the query.
        """
        n = self._num_documents

        # Retrieve all documents for each query
        indices, scores = self._retriever.retrieve(
            self._tokens, k=n, show_progress=False,
        )

        # Build a dense N×N score matrix
        matrix: list[list[float]] = [[0.0] * n for _ in range(n)]
        for query_idx in range(n):
            for rank_pos in range(n):
                doc_idx = int(indices[query_idx, rank_pos])
                score = float(scores[query_idx, rank_pos])
                if doc_idx != query_idx:
                    matrix[query_idx][doc_idx] = score

        return matrix
