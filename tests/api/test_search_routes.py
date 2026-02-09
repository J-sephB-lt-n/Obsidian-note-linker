"""Tests for document search routes."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obsidian_note_linker.api.app import create_app
from obsidian_note_linker.domain.note import compute_content_hash
from obsidian_note_linker.infrastructure.embedding_store import save_embeddings
from obsidian_note_linker.infrastructure.note_store import upsert_note_record
from obsidian_note_linker.services.config_service import ConfigService


class _FakeEmbeddingProvider:
    """Deterministic embedding provider for testing."""

    @property
    def model_name(self) -> str:
        return "fake-model"

    @property
    def dimension(self) -> int:
        return 3

    def embed(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            length = float(len(text))
            results.append([length, length / 2.0, 1.0])
        return results


def _setup_indexed_vault(
    vault_path: Path,
    app: object,
) -> None:
    """Create indexed notes in the vault and DB for a configured app."""
    from obsidian_note_linker.domain.markdown_stripper import prepare_note_for_embedding

    notes = {
        "machine-learning.md": "# Machine Learning\n\nNeural networks and deep learning algorithms.",
        "cooking.md": "# Cooking\n\nItalian pasta recipes and sauce techniques.",
        "ai-research.md": "# AI Research\n\nAdvances in machine learning and neural networks.",
    }

    provider = _FakeEmbeddingProvider()
    engine = app.state.db_engine  # type: ignore[union-attr]

    content_hashes: list[str] = []
    texts: list[str] = []

    for rel_path, content in notes.items():
        file_path = vault_path / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        content_hash = compute_content_hash(content)
        upsert_note_record(
            engine=engine,
            relative_path=rel_path,
            content_hash=content_hash,
        )
        content_hashes.append(content_hash)
        title = Path(rel_path).stem
        texts.append(prepare_note_for_embedding(title=title, content=content))

    embeddings = provider.embed(texts)
    save_embeddings(
        engine=engine,
        content_hashes=content_hashes,
        embeddings=embeddings,
        model_name=provider.model_name,
        dimension=provider.dimension,
    )

    app.state.embedding_provider = provider  # type: ignore[union-attr]


@pytest.fixture
def configured_app(tmp_path: Path) -> object:
    """Create a configured FastAPI app with a vault."""
    config_path = tmp_path / "config" / "config.json"
    vault = tmp_path / "vault"
    vault.mkdir()
    svc = ConfigService(config_path=config_path)
    svc.save_vault_path(vault_path=vault)
    app = create_app(config_path=config_path)
    return app


@pytest.fixture
def client_with_config(configured_app: object) -> TestClient:
    """Test client with a configured vault (no indexed notes)."""
    return TestClient(configured_app, follow_redirects=False)  # type: ignore[arg-type]


@pytest.fixture
def vault_path(configured_app: object) -> Path:
    """Return the vault path from the configured app."""
    config = configured_app.state.config_service.load_config()  # type: ignore[union-attr]
    return config.vault_path


@pytest.fixture
def client_with_indexed_notes(
    configured_app: object,
    vault_path: Path,
) -> TestClient:
    """Test client with a configured vault and indexed notes."""
    _setup_indexed_vault(vault_path=vault_path, app=configured_app)
    return TestClient(configured_app, follow_redirects=False)  # type: ignore[arg-type]


class TestSearchPage:
    """Tests for the main search page."""

    def test_search_page_renders(self, client_with_config: TestClient) -> None:
        response = client_with_config.get("/search")
        assert response.status_code == 200
        assert "Search" in response.text

    def test_search_page_has_query_input(self, client_with_config: TestClient) -> None:
        response = client_with_config.get("/search")
        assert 'name="q"' in response.text

    def test_search_page_has_mode_selector(self, client_with_config: TestClient) -> None:
        response = client_with_config.get("/search")
        assert "hybrid" in response.text.lower()
        assert "fts" in response.text.lower() or "full-text" in response.text.lower()
        assert "semantic" in response.text.lower()

    def test_search_page_default_mode_is_hybrid(
        self, client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/search")
        # Hybrid radio should be checked by default
        assert 'value="hybrid"' in response.text

    def test_search_page_in_navigation(self, client_with_config: TestClient) -> None:
        response = client_with_config.get("/search")
        assert '<a href="/search">' in response.text


class TestSearchResults:
    """Tests for the search results endpoint."""

    def test_search_results_fts(
        self, client_with_indexed_notes: TestClient,
    ) -> None:
        response = client_with_indexed_notes.get(
            "/search/results", params={"q": "machine learning", "mode": "fts"},
        )
        assert response.status_code == 200
        assert "Machine Learning" in response.text

    def test_search_results_semantic(
        self, client_with_indexed_notes: TestClient,
    ) -> None:
        response = client_with_indexed_notes.get(
            "/search/results", params={"q": "neural networks", "mode": "semantic"},
        )
        assert response.status_code == 200

    def test_search_results_hybrid(
        self, client_with_indexed_notes: TestClient,
    ) -> None:
        response = client_with_indexed_notes.get(
            "/search/results", params={"q": "machine learning", "mode": "hybrid"},
        )
        assert response.status_code == 200

    def test_search_results_show_title(
        self, client_with_indexed_notes: TestClient,
    ) -> None:
        response = client_with_indexed_notes.get(
            "/search/results", params={"q": "pasta recipes", "mode": "fts"},
        )
        assert "Cooking" in response.text

    def test_search_results_show_score(
        self, client_with_indexed_notes: TestClient,
    ) -> None:
        response = client_with_indexed_notes.get(
            "/search/results", params={"q": "machine learning", "mode": "fts"},
        )
        # Score should appear as a number
        assert "Score" in response.text or "score" in response.text

    def test_search_results_show_snippet(
        self, client_with_indexed_notes: TestClient,
    ) -> None:
        response = client_with_indexed_notes.get(
            "/search/results", params={"q": "machine learning", "mode": "fts"},
        )
        # Snippet from the note content (markdown stripped)
        assert "Neural networks" in response.text or "neural networks" in response.text.lower()

    def test_search_results_show_result_count(
        self, client_with_indexed_notes: TestClient,
    ) -> None:
        response = client_with_indexed_notes.get(
            "/search/results", params={"q": "machine learning", "mode": "fts"},
        )
        assert "result" in response.text.lower()

    def test_search_results_empty_query(
        self, client_with_indexed_notes: TestClient,
    ) -> None:
        response = client_with_indexed_notes.get(
            "/search/results", params={"q": "", "mode": "fts"},
        )
        assert response.status_code == 200

    def test_search_results_no_matching_terms(
        self, client_with_indexed_notes: TestClient,
    ) -> None:
        response = client_with_indexed_notes.get(
            "/search/results", params={"q": "zzzznonexistent", "mode": "fts"},
        )
        assert response.status_code == 200
        assert "0 result" in response.text or "No results" in response.text

    def test_search_warns_when_no_notes_indexed(
        self, client_with_config: TestClient,
    ) -> None:
        """FR7.9: Warn if notes have not yet been indexed."""
        response = client_with_config.get(
            "/search/results", params={"q": "test", "mode": "fts"},
        )
        assert response.status_code == 200
        assert "index" in response.text.lower()

    def test_search_warns_semantic_without_provider(
        self, client_with_config: TestClient,
    ) -> None:
        """Semantic search without provider should show warning."""
        response = client_with_config.get(
            "/search/results", params={"q": "test", "mode": "semantic"},
        )
        assert response.status_code == 200
        assert "index" in response.text.lower() or "embedding" in response.text.lower()

    def test_search_results_have_view_button(
        self, client_with_indexed_notes: TestClient,
    ) -> None:
        """Each result should have a way to view the full note."""
        response = client_with_indexed_notes.get(
            "/search/results", params={"q": "machine learning", "mode": "fts"},
        )
        assert "/search/note" in response.text


class TestSearchNoteView:
    """Tests for the expanded note view endpoint."""

    def test_view_note_renders_content(
        self, client_with_indexed_notes: TestClient,
    ) -> None:
        response = client_with_indexed_notes.get(
            "/search/note", params={"path": "machine-learning.md"},
        )
        assert response.status_code == 200
        # Content should be rendered as HTML (mistune)
        assert "Neural networks" in response.text or "neural networks" in response.text.lower()

    def test_view_note_shows_title(
        self, client_with_indexed_notes: TestClient,
    ) -> None:
        response = client_with_indexed_notes.get(
            "/search/note", params={"path": "cooking.md"},
        )
        assert response.status_code == 200
        assert "Cooking" in response.text

    def test_view_note_not_found(
        self, client_with_indexed_notes: TestClient,
    ) -> None:
        response = client_with_indexed_notes.get(
            "/search/note", params={"path": "nonexistent.md"},
        )
        assert response.status_code == 404

    def test_view_note_has_close_mechanism(
        self, client_with_indexed_notes: TestClient,
    ) -> None:
        response = client_with_indexed_notes.get(
            "/search/note", params={"path": "machine-learning.md"},
        )
        assert response.status_code == 200
        # Should have a way to close/collapse the note view
        assert "close" in response.text.lower() or "collapse" in response.text.lower()
