"""Tests for the document search service."""

from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from obsidian_note_linker.domain.embedding_provider import EmbeddingProvider
from obsidian_note_linker.domain.search import SearchMode, SearchResult
from obsidian_note_linker.infrastructure.embedding_store import save_embeddings
from obsidian_note_linker.infrastructure.note_store import upsert_note_record
from obsidian_note_linker.services.search_service import SearchService


class _FakeEmbeddingProvider:
    """Deterministic embedding provider for testing."""

    @property
    def model_name(self) -> str:
        return "fake-model"

    @property
    def dimension(self) -> int:
        return 3

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate simple deterministic embeddings based on text length."""
        results: list[list[float]] = []
        for text in texts:
            length = float(len(text))
            results.append([length, length / 2.0, 1.0])
        return results


def _setup_indexed_vault(
    vault_path: Path,
    db_engine: Engine,
    notes: dict[str, str],
    provider: EmbeddingProvider,
) -> None:
    """Create note files, DB records, and embeddings for a set of notes.

    Args:
        vault_path: Path to the temporary vault directory.
        db_engine: SQLAlchemy engine.
        notes: Mapping of relative_path → content.
        provider: Embedding provider for generating embeddings.
    """
    from obsidian_note_linker.domain.markdown_stripper import prepare_note_for_embedding
    from obsidian_note_linker.domain.note import compute_content_hash

    content_hashes: list[str] = []
    texts: list[str] = []

    for rel_path, content in notes.items():
        # Create note file
        file_path = vault_path / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        # Create DB records
        content_hash = compute_content_hash(content)
        upsert_note_record(
            engine=db_engine,
            relative_path=rel_path,
            content_hash=content_hash,
        )

        content_hashes.append(content_hash)
        title = Path(rel_path).stem
        texts.append(prepare_note_for_embedding(title=title, content=content))

    # Save embeddings
    embeddings = provider.embed(texts)
    save_embeddings(
        engine=db_engine,
        content_hashes=content_hashes,
        embeddings=embeddings,
        model_name=provider.model_name,
        dimension=provider.dimension,
    )


@pytest.fixture
def provider() -> _FakeEmbeddingProvider:
    """Return a fake embedding provider."""
    return _FakeEmbeddingProvider()


@pytest.fixture
def sample_notes() -> dict[str, str]:
    """Return a set of sample notes for testing."""
    return {
        "machine-learning.md": "# Machine Learning\n\nNeural networks and deep learning algorithms.",
        "cooking.md": "# Cooking\n\nItalian pasta recipes and sauce techniques.",
        "ai-research.md": "# AI Research\n\nAdvances in machine learning and neural networks.",
    }


@pytest.fixture
def indexed_vault(
    vault_path: Path,
    db_engine: Engine,
    sample_notes: dict[str, str],
    provider: _FakeEmbeddingProvider,
) -> Path:
    """Set up an indexed vault with sample notes."""
    _setup_indexed_vault(
        vault_path=vault_path,
        db_engine=db_engine,
        notes=sample_notes,
        provider=provider,
    )
    return vault_path


class TestSearchServiceFTS:
    """Tests for full-text search mode."""

    def test_fts_returns_results(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        service = SearchService(engine=db_engine, vault_path=indexed_vault)
        results = service.search(query="machine learning", mode=SearchMode.FTS)
        assert len(results) > 0

    def test_fts_results_are_search_results(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        service = SearchService(engine=db_engine, vault_path=indexed_vault)
        results = service.search(query="machine learning", mode=SearchMode.FTS)
        for result in results:
            assert isinstance(result, SearchResult)

    def test_fts_relevant_doc_ranks_higher(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        service = SearchService(engine=db_engine, vault_path=indexed_vault)
        results = service.search(query="pasta recipes cooking", mode=SearchMode.FTS)
        assert results[0].title == "Cooking", "Cooking note should rank first for cooking query"

    def test_fts_results_have_scores(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        service = SearchService(engine=db_engine, vault_path=indexed_vault)
        results = service.search(query="machine", mode=SearchMode.FTS)
        for result in results:
            assert result.score >= 0.0

    def test_fts_results_sorted_by_score_descending(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        service = SearchService(engine=db_engine, vault_path=indexed_vault)
        results = service.search(query="learning", mode=SearchMode.FTS)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_fts_results_have_snippets(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        service = SearchService(engine=db_engine, vault_path=indexed_vault)
        results = service.search(query="machine", mode=SearchMode.FTS)
        for result in results:
            assert isinstance(result.snippet, str)

    def test_fts_results_have_titles(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        service = SearchService(engine=db_engine, vault_path=indexed_vault)
        results = service.search(query="machine", mode=SearchMode.FTS)
        titles = {r.title for r in results}
        assert "Machine Learning" in titles or "machine-learning" in titles

    def test_fts_does_not_require_embedding_provider(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        """FTS mode should work without an embedding provider."""
        service = SearchService(
            engine=db_engine,
            vault_path=indexed_vault,
            embedding_provider=None,
        )
        results = service.search(query="machine", mode=SearchMode.FTS)
        assert len(results) > 0

    def test_fts_top_k_limits_results(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        service = SearchService(engine=db_engine, vault_path=indexed_vault)
        results = service.search(
            query="machine", mode=SearchMode.FTS, top_k=1,
        )
        assert len(results) <= 1

    def test_fts_excludes_zero_score_results(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        """Results with zero BM25 score (no matching terms) should be excluded."""
        service = SearchService(engine=db_engine, vault_path=indexed_vault)
        results = service.search(
            query="zzzznonexistentterm", mode=SearchMode.FTS,
        )
        assert len(results) == 0


class TestSearchServiceSemantic:
    """Tests for semantic search mode."""

    def test_semantic_returns_results(
        self, db_engine: Engine, indexed_vault: Path, provider: _FakeEmbeddingProvider,
    ) -> None:
        service = SearchService(
            engine=db_engine,
            vault_path=indexed_vault,
            embedding_provider=provider,
        )
        results = service.search(query="neural networks", mode=SearchMode.SEMANTIC)
        assert len(results) > 0

    def test_semantic_results_sorted_by_score_descending(
        self, db_engine: Engine, indexed_vault: Path, provider: _FakeEmbeddingProvider,
    ) -> None:
        service = SearchService(
            engine=db_engine,
            vault_path=indexed_vault,
            embedding_provider=provider,
        )
        results = service.search(query="test query", mode=SearchMode.SEMANTIC)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_semantic_requires_embedding_provider(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        """Semantic mode without embedding provider should raise ValueError."""
        service = SearchService(
            engine=db_engine,
            vault_path=indexed_vault,
            embedding_provider=None,
        )
        with pytest.raises(ValueError, match="[Ee]mbedding provider"):
            service.search(query="test", mode=SearchMode.SEMANTIC)

    def test_semantic_top_k_limits_results(
        self, db_engine: Engine, indexed_vault: Path, provider: _FakeEmbeddingProvider,
    ) -> None:
        service = SearchService(
            engine=db_engine,
            vault_path=indexed_vault,
            embedding_provider=provider,
        )
        results = service.search(
            query="test", mode=SearchMode.SEMANTIC, top_k=1,
        )
        assert len(results) <= 1


class TestSearchServiceHybrid:
    """Tests for hybrid search mode."""

    def test_hybrid_returns_results(
        self, db_engine: Engine, indexed_vault: Path, provider: _FakeEmbeddingProvider,
    ) -> None:
        service = SearchService(
            engine=db_engine,
            vault_path=indexed_vault,
            embedding_provider=provider,
        )
        results = service.search(query="machine learning", mode=SearchMode.HYBRID)
        assert len(results) > 0

    def test_hybrid_results_sorted_by_score_descending(
        self, db_engine: Engine, indexed_vault: Path, provider: _FakeEmbeddingProvider,
    ) -> None:
        service = SearchService(
            engine=db_engine,
            vault_path=indexed_vault,
            embedding_provider=provider,
        )
        results = service.search(query="machine learning", mode=SearchMode.HYBRID)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_hybrid_requires_embedding_provider(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        service = SearchService(
            engine=db_engine,
            vault_path=indexed_vault,
            embedding_provider=None,
        )
        with pytest.raises(ValueError, match="[Ee]mbedding provider"):
            service.search(query="test", mode=SearchMode.HYBRID)

    def test_hybrid_top_k_limits_results(
        self, db_engine: Engine, indexed_vault: Path, provider: _FakeEmbeddingProvider,
    ) -> None:
        service = SearchService(
            engine=db_engine,
            vault_path=indexed_vault,
            embedding_provider=provider,
        )
        results = service.search(
            query="test", mode=SearchMode.HYBRID, top_k=1,
        )
        assert len(results) <= 1


class TestSearchServiceEdgeCases:
    """Tests for edge cases and readiness checking."""

    def test_empty_query_returns_no_results(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        service = SearchService(engine=db_engine, vault_path=indexed_vault)
        results = service.search(query="", mode=SearchMode.FTS)
        assert results == []

    def test_whitespace_only_query_returns_no_results(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        service = SearchService(engine=db_engine, vault_path=indexed_vault)
        results = service.search(query="   ", mode=SearchMode.FTS)
        assert results == []

    def test_no_indexed_notes_returns_no_results(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        """Search with no indexed notes should return an empty list."""
        service = SearchService(engine=db_engine, vault_path=vault_path)
        results = service.search(query="test", mode=SearchMode.FTS)
        assert results == []

    def test_check_readiness_no_indexed_notes(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        service = SearchService(engine=db_engine, vault_path=vault_path)
        warning = service.check_readiness(mode=SearchMode.FTS)
        assert warning is not None
        assert "index" in warning.lower()

    def test_check_readiness_fts_with_indexed_notes(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        service = SearchService(engine=db_engine, vault_path=indexed_vault)
        warning = service.check_readiness(mode=SearchMode.FTS)
        assert warning is None

    def test_check_readiness_semantic_without_provider(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        service = SearchService(
            engine=db_engine,
            vault_path=indexed_vault,
            embedding_provider=None,
        )
        warning = service.check_readiness(mode=SearchMode.SEMANTIC)
        assert warning is not None
        assert "embedding" in warning.lower()

    def test_check_readiness_semantic_with_provider(
        self, db_engine: Engine, indexed_vault: Path, provider: _FakeEmbeddingProvider,
    ) -> None:
        service = SearchService(
            engine=db_engine,
            vault_path=indexed_vault,
            embedding_provider=provider,
        )
        warning = service.check_readiness(mode=SearchMode.SEMANTIC)
        assert warning is None

    def test_check_readiness_hybrid_without_provider(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        service = SearchService(
            engine=db_engine,
            vault_path=indexed_vault,
            embedding_provider=None,
        )
        warning = service.check_readiness(mode=SearchMode.HYBRID)
        assert warning is not None

    def test_results_have_correct_relative_paths(
        self, db_engine: Engine, indexed_vault: Path,
    ) -> None:
        service = SearchService(engine=db_engine, vault_path=indexed_vault)
        results = service.search(query="machine learning", mode=SearchMode.FTS)
        for result in results:
            assert str(result.relative_path).endswith(".md")

    def test_subdirectory_notes(
        self, db_engine: Engine, vault_path: Path, provider: _FakeEmbeddingProvider,
    ) -> None:
        """Notes in subdirectories should be found and have correct paths."""
        notes = {
            "subdir/deep-note.md": "# Deep Note\n\nA note in a subdirectory about testing.",
        }
        _setup_indexed_vault(
            vault_path=vault_path,
            db_engine=db_engine,
            notes=notes,
            provider=provider,
        )
        service = SearchService(
            engine=db_engine,
            vault_path=vault_path,
            embedding_provider=provider,
        )
        results = service.search(query="testing", mode=SearchMode.FTS)
        assert len(results) == 1
        assert results[0].relative_path == Path("subdir/deep-note.md")
