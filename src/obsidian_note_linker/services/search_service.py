"""Document search service — FTS, semantic, and hybrid search.

Orchestrates document search by combining BM25 lexical retrieval,
embedding-based semantic similarity, and Reciprocal Rank Fusion for
hybrid ranking.  Reuses the same indexed data as the candidate
generation pipeline.
"""

import logging
import time
from pathlib import Path

from sqlalchemy.engine import Engine

from obsidian_note_linker.domain.embedding_provider import EmbeddingProvider
from obsidian_note_linker.domain.markdown_stripper import prepare_note_for_embedding
from obsidian_note_linker.domain.ranking import compute_rrf_score, ranks_from_scores
from obsidian_note_linker.domain.search import SearchMode, SearchResult, generate_snippet
from obsidian_note_linker.infrastructure.bm25_index import BM25Index
from obsidian_note_linker.infrastructure.embedding_store import get_all_embeddings
from obsidian_note_linker.infrastructure.note_store import get_all_note_records
from obsidian_note_linker.infrastructure.similarity import (
    compute_query_cosine_similarity,
)

logger = logging.getLogger(__name__)


class _CorpusEntry:
    """Internal container for a loaded note and its metadata.

    Attributes:
        relative_path: Path relative to vault root.
        content_hash: SHA256 hash of the raw content.
        raw_content: Original markdown content (for snippet generation).
        prepared_text: Cleaned text for BM25 indexing.
        title: Note title (filename stem).
    """

    __slots__ = (
        "relative_path",
        "content_hash",
        "raw_content",
        "prepared_text",
        "title",
    )

    def __init__(
        self,
        relative_path: str,
        content_hash: str,
        raw_content: str,
        prepared_text: str,
        title: str,
    ) -> None:
        self.relative_path = relative_path
        self.content_hash = content_hash
        self.raw_content = raw_content
        self.prepared_text = prepared_text
        self.title = title


def _display_title(stem: str) -> str:
    """Convert a filename stem to a human-readable display title.

    Replaces hyphens and underscores with spaces and applies title
    casing (e.g. ``"machine-learning"`` → ``"Machine Learning"``).

    Args:
        stem: Filename without the ``.md`` extension.

    Returns:
        Human-readable title string.
    """
    return stem.replace("-", " ").replace("_", " ").title()


class SearchService:
    """Orchestrates document search across FTS, semantic, and hybrid modes.

    Loads indexed notes and embeddings from the database, builds a BM25
    index lazily on the first search, and delegates to mode-specific
    search methods.

    Args:
        engine: SQLAlchemy engine for database access.
        vault_path: Absolute path to the Obsidian vault.
        embedding_provider: Optional embedding provider for semantic
                           and hybrid search modes.
    """

    def __init__(
        self,
        engine: Engine,
        vault_path: Path,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._engine = engine
        self._vault_path = vault_path
        self._embedding_provider = embedding_provider

    def search(
        self,
        query: str,
        mode: SearchMode,
        top_k: int = 20,
    ) -> list[SearchResult]:
        """Search indexed notes using the specified mode.

        Args:
            query: Free-text search query.
            mode: Search mode (FTS, SEMANTIC, or HYBRID).
            top_k: Maximum number of results to return.

        Returns:
            List of search results sorted by relevance (highest first).

        Raises:
            ValueError: If semantic/hybrid mode is requested without
                       an embedding provider.
        """
        if not query or not query.strip():
            return []

        logger.info("Search: query=%r, mode=%s, top_k=%d", query, mode.value, top_k)
        search_start = time.perf_counter()

        corpus = self._load_corpus()
        if not corpus:
            logger.info("Search aborted: no indexed notes in corpus")
            return []

        if mode == SearchMode.FTS:
            results = self._search_fts(
                query=query, corpus=corpus, top_k=top_k,
            )
        elif mode == SearchMode.SEMANTIC:
            results = self._search_semantic(
                query=query, corpus=corpus, top_k=top_k,
            )
        else:
            results = self._search_hybrid(
                query=query, corpus=corpus, top_k=top_k,
            )

        logger.info(
            "Search complete: %d results for query=%r (%.2fs)",
            len(results), query, time.perf_counter() - search_start,
        )
        return results

    def check_readiness(self, mode: SearchMode) -> str | None:
        """Check whether the search index is ready for the given mode.

        Args:
            mode: Search mode to check readiness for.

        Returns:
            A warning message if the index is not ready, or ``None``
            if search can proceed.
        """
        note_records = get_all_note_records(self._engine)

        if not note_records:
            return (
                "No notes have been indexed yet. "
                "Run indexing from the Dashboard first."
            )

        if mode in (SearchMode.SEMANTIC, SearchMode.HYBRID):
            if self._embedding_provider is None:
                return (
                    "Embedding provider not available. "
                    "Run indexing from the Dashboard to load the model."
                )

            all_embeddings = get_all_embeddings(self._engine)
            if not all_embeddings:
                return (
                    "No embeddings have been computed yet. "
                    "Run indexing from the Dashboard first."
                )

        return None

    def _load_corpus(self) -> list[_CorpusEntry]:
        """Load all indexed notes with their content from the vault.

        Returns:
            List of corpus entries with paths, content, and hashes.
            Empty list if no notes are indexed.
        """
        t0 = time.perf_counter()
        note_records = get_all_note_records(self._engine)
        if not note_records:
            return []

        entries: list[_CorpusEntry] = []
        for record in note_records:
            note_path = self._vault_path / record.relative_path
            if not note_path.is_file():
                logger.warning(
                    "Indexed note no longer exists: %s", record.relative_path,
                )
                continue

            content = note_path.read_text(encoding="utf-8")
            title = Path(record.relative_path).stem
            prepared_text = prepare_note_for_embedding(
                title=title, content=content,
            )

            entries.append(_CorpusEntry(
                relative_path=record.relative_path,
                content_hash=record.content_hash,
                raw_content=content,
                prepared_text=prepared_text,
                title=title,
            ))

        logger.debug(
            "Loaded corpus: %d entries (%.2fs)",
            len(entries), time.perf_counter() - t0,
        )
        return entries

    def _search_fts(
        self,
        query: str,
        corpus: list[_CorpusEntry],
        top_k: int,
    ) -> list[SearchResult]:
        """Full-text search using BM25 lexical ranking."""
        t0 = time.perf_counter()
        texts = [entry.prepared_text for entry in corpus]
        bm25_index = BM25Index(texts)

        results: list[SearchResult] = []
        for doc_idx, score in bm25_index.query(query_text=query, top_k=top_k):
            if score <= 0.0:
                continue
            entry = corpus[doc_idx]
            results.append(SearchResult(
                relative_path=Path(entry.relative_path),
                title=_display_title(entry.title),
                score=round(score, 4),
                snippet=generate_snippet(entry.raw_content),
            ))

        logger.debug("FTS search completed (%.2fs)", time.perf_counter() - t0)
        return results

    def _search_semantic(
        self,
        query: str,
        corpus: list["_CorpusEntry"],
        top_k: int,
    ) -> list[SearchResult]:
        """Semantic search using embedding cosine similarity."""
        t0 = time.perf_counter()
        if self._embedding_provider is None:
            raise ValueError(
                "Embedding provider is required for semantic search"
            )

        all_embeddings = get_all_embeddings(self._engine)

        # Align embeddings with corpus order
        corpus_embeddings: list[list[float]] = []
        valid_entries: list[_CorpusEntry] = []
        for entry in corpus:
            emb = all_embeddings.get(entry.content_hash)
            if emb is not None:
                corpus_embeddings.append(emb)
                valid_entries.append(entry)

        if not corpus_embeddings:
            return []

        # Embed query
        query_embedding = self._embedding_provider.embed([query])[0]

        # Compute similarities
        similarities = compute_query_cosine_similarity(
            query_embedding=query_embedding,
            corpus_embeddings=corpus_embeddings,
        )

        # Build scored results and sort
        scored = list(zip(valid_entries, similarities))
        scored.sort(key=lambda x: x[1], reverse=True)

        results: list[SearchResult] = []
        for entry, score in scored[:top_k]:
            results.append(SearchResult(
                relative_path=Path(entry.relative_path),
                title=_display_title(entry.title),
                score=round(score, 4),
                snippet=generate_snippet(entry.raw_content),
            ))

        logger.debug("Semantic search completed (%.2fs)", time.perf_counter() - t0)
        return results

    def _search_hybrid(
        self,
        query: str,
        corpus: list["_CorpusEntry"],
        top_k: int,
    ) -> list[SearchResult]:
        """Hybrid search combining FTS and semantic via RRF."""
        t0 = time.perf_counter()
        if self._embedding_provider is None:
            raise ValueError(
                "Embedding provider is required for hybrid search"
            )

        all_embeddings = get_all_embeddings(self._engine)

        # Filter corpus to entries that have embeddings
        valid_entries: list[_CorpusEntry] = []
        corpus_embeddings: list[list[float]] = []
        for entry in corpus:
            emb = all_embeddings.get(entry.content_hash)
            if emb is not None:
                valid_entries.append(entry)
                corpus_embeddings.append(emb)

        if not valid_entries:
            return []

        # BM25 scores
        texts = [entry.prepared_text for entry in valid_entries]
        bm25_index = BM25Index(texts)
        bm25_scores = bm25_index.query_all_scores(query_text=query)

        # Semantic scores
        query_embedding = self._embedding_provider.embed([query])[0]
        semantic_scores = compute_query_cosine_similarity(
            query_embedding=query_embedding,
            corpus_embeddings=corpus_embeddings,
        )

        # Convert to ranks and compute RRF
        bm25_ranks = ranks_from_scores(bm25_scores)
        semantic_ranks = ranks_from_scores(semantic_scores)

        rrf_scores: list[float] = []
        for i in range(len(valid_entries)):
            rrf = compute_rrf_score(
                semantic_rank=semantic_ranks[i],
                lexical_rank=bm25_ranks[i],
            )
            rrf_scores.append(rrf)

        # Build scored results and sort
        scored = list(zip(valid_entries, rrf_scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        results: list[SearchResult] = []
        for entry, score in scored[:top_k]:
            results.append(SearchResult(
                relative_path=Path(entry.relative_path),
                title=_display_title(entry.title),
                score=round(score, 4),
                snippet=generate_snippet(entry.raw_content),
            ))

        logger.debug("Hybrid search completed (%.2fs)", time.perf_counter() - t0)
        return results
