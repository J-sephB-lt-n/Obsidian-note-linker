"""Tests for indexing API routes."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obsidian_note_linker.api.app import create_app
from obsidian_note_linker.services.config_service import ConfigService


class _FakeEmbeddingProvider:
    """Fast fake embedding provider for route tests.

    Returns slightly different embeddings per text (based on length)
    so pairwise similarity is meaningful.
    """

    @property
    def model_name(self) -> str:
        return "fake-model"

    @property
    def dimension(self) -> int:
        return 3

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1 + i * 0.01, 0.2 + i * 0.02, 0.3] for i, _ in enumerate(texts)]


@pytest.fixture
def vault_with_notes(tmp_path: Path) -> Path:
    """Create a temporary vault with some markdown notes."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note1.md").write_text("# Note One\n\nHello world", encoding="utf-8")
    (vault / "note2.md").write_text("# Note Two\n\nGoodbye world", encoding="utf-8")
    return vault


@pytest.fixture
def client_with_notes(
    tmp_path: Path,
    vault_with_notes: Path,
) -> TestClient:
    """Test client with a configured vault containing notes and a fake provider."""
    config_path = tmp_path / "config" / "config.json"
    svc = ConfigService(config_path=config_path)
    svc.save_vault_path(vault_path=vault_with_notes)

    app = create_app(config_path=config_path)
    app.state.embedding_provider = _FakeEmbeddingProvider()
    return TestClient(app, follow_redirects=False)


class TestDashboardIndexingStatus:
    """Tests for indexing status display on the dashboard."""

    def test_shows_notes_in_vault_count(
        self, client_with_notes: TestClient,
    ) -> None:
        response = client_with_notes.get("/")

        assert response.status_code == 200
        assert "Notes in Vault" in response.text

    def test_shows_notes_needing_indexing(
        self, client_with_notes: TestClient,
    ) -> None:
        response = client_with_notes.get("/")

        assert "need indexing" in response.text

    def test_shows_index_now_button(
        self, client_with_notes: TestClient,
    ) -> None:
        response = client_with_notes.get("/")

        assert "Index Now" in response.text
        assert 'hx-get="/indexing/start"' in response.text


class TestIndexingStart:
    """Tests for the /indexing/start endpoint."""

    def test_returns_sse_connected_html(
        self, client_with_notes: TestClient,
    ) -> None:
        response = client_with_notes.get("/indexing/start")

        assert response.status_code == 200
        assert "sse-connect" in response.text
        assert "/indexing/stream" in response.text

    def test_returns_409_when_already_indexing(
        self, client_with_notes: TestClient,
    ) -> None:
        client_with_notes.app.state.is_indexing = True  # type: ignore[union-attr]

        response = client_with_notes.get("/indexing/start")

        assert response.status_code == 409
        client_with_notes.app.state.is_indexing = False  # type: ignore[union-attr]


class TestIndexingStream:
    """Tests for the /indexing/stream SSE endpoint."""

    def test_returns_sse_content_type(
        self, client_with_notes: TestClient,
    ) -> None:
        response = client_with_notes.get("/indexing/stream")

        assert "text/event-stream" in response.headers["content-type"]

    def test_streams_progress_events(
        self, client_with_notes: TestClient,
    ) -> None:
        response = client_with_notes.get("/indexing/stream")
        body = response.text

        assert "event: progress" in body, "Should contain progress events"
        assert "event: complete" in body, "Should contain completion event"

    def test_complete_event_contains_summary(
        self, client_with_notes: TestClient,
    ) -> None:
        response = client_with_notes.get("/indexing/stream")
        body = response.text

        assert "Indexing Complete" in body
        assert "Added:" in body

    def test_indexes_notes_and_updates_dashboard(
        self, client_with_notes: TestClient,
    ) -> None:
        # Run indexing
        client_with_notes.get("/indexing/stream")

        # Dashboard should now show notes as indexed
        dashboard = client_with_notes.get("/")

        assert "All notes indexed" in dashboard.text

    def test_resets_is_indexing_flag_on_completion(
        self, client_with_notes: TestClient,
    ) -> None:
        client_with_notes.get("/indexing/stream")

        assert client_with_notes.app.state.is_indexing is False  # type: ignore[union-attr]

    def test_generates_candidates_after_indexing(
        self, client_with_notes: TestClient,
    ) -> None:
        response = client_with_notes.get("/indexing/stream")
        body = response.text

        assert "Candidates found:" in body
        assert "Generating candidates" in body

    def test_sets_candidate_count_in_app_state(
        self, client_with_notes: TestClient,
    ) -> None:
        client_with_notes.get("/indexing/stream")

        count = client_with_notes.app.state.candidate_count  # type: ignore[union-attr]
        assert isinstance(count, int)
        assert count >= 0

    def test_dashboard_shows_candidate_count_after_indexing(
        self, client_with_notes: TestClient,
    ) -> None:
        client_with_notes.get("/indexing/stream")

        dashboard = client_with_notes.get("/")
        assert "Pairs to review" in dashboard.text
