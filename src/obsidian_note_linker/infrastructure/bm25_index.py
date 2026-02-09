"""BM25 lexical index wrapper using bm25s.

Provides an in-memory BM25 index for computing pairwise lexical
similarity scores between notes and single-query retrieval for
document search.  The index is rebuilt each time indexing is
triggered (not persisted to disk).
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

    def query(self, query_text: str, top_k: int = 10) -> list[tuple[int, float]]:
        """Retrieve the top-k documents matching a free-text query.

        Args:
            query_text: Plain-text search query.
            top_k: Maximum number of results to return.  Clamped to
                   the corpus size if larger.

        Returns:
            List of ``(doc_index, score)`` tuples sorted by score
            descending.  Scores are non-negative BM25 values.
        """
        k = min(top_k, self._num_documents)
        query_tokens = bm25s.tokenize([query_text], show_progress=False)
        indices, scores = self._retriever.retrieve(
            query_tokens, k=k, show_progress=False,
        )

        results: list[tuple[int, float]] = []
        for rank_pos in range(k):
            doc_idx = int(indices[0, rank_pos])
            score = float(scores[0, rank_pos])
            results.append((doc_idx, score))

        return results

    def query_all_scores(self, query_text: str) -> list[float]:
        """Compute BM25 scores for all documents against a query.

        Returns a score for every document in corpus order, suitable
        for rank conversion and hybrid combination.

        Args:
            query_text: Plain-text search query.

        Returns:
            List of BM25 scores, one per document, in corpus order.
        """
        n = self._num_documents
        query_tokens = bm25s.tokenize([query_text], show_progress=False)
        indices, scores = self._retriever.retrieve(
            query_tokens, k=n, show_progress=False,
        )

        result = [0.0] * n
        for rank_pos in range(n):
            doc_idx = int(indices[0, rank_pos])
            result[doc_idx] = float(scores[0, rank_pos])

        return result
