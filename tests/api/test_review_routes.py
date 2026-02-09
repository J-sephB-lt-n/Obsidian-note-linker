"""Tests for review routes."""

from pathlib import Path

from fastapi.testclient import TestClient

from obsidian_note_linker.domain.candidate import CandidatePair
from obsidian_note_linker.domain.note import compute_content_hash
from obsidian_note_linker.infrastructure.note_store import upsert_note_record


def _make_candidate(
    note_a: str,
    note_b: str,
    rrf_score: float = 0.03,
) -> CandidatePair:
    """Create a CandidatePair with minimal required fields for testing."""
    return CandidatePair(
        note_a_path=Path(note_a),
        note_b_path=Path(note_b),
        semantic_similarity=0.8,
        semantic_rank_a_to_b=1,
        semantic_rank_b_to_a=1,
        lexical_score_a_to_b=5.0,
        lexical_score_b_to_a=4.0,
        lexical_rank_a_to_b=1,
        lexical_rank_b_to_a=1,
        rrf_score=rrf_score,
    )


def _setup_review_vault(client: TestClient, notes: dict[str, str]) -> None:
    """Create note files on disk and insert records into the DB.

    Also sets up candidates in app.state for the given notes.
    """
    config = client.app.state.config_service.load_config()  # type: ignore[union-attr]
    vault_path = config.vault_path
    engine = client.app.state.db_engine  # type: ignore[union-attr]

    for rel_path, content in notes.items():
        full_path = vault_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        upsert_note_record(
            engine=engine,
            relative_path=rel_path,
            content_hash=compute_content_hash(content),
        )


class TestReviewPage:
    """Tests for GET /review."""

    def test_shows_review_page_when_configured(
        self, client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/review")
        assert response.status_code == 200
        assert "Review" in response.text

    def test_shows_no_candidates_message_when_none_available(
        self, client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/review")
        assert response.status_code == 200
        assert "No Candidates Available" in response.text

    def test_shows_target_selection_when_candidates_exist(
        self, client_with_config: TestClient,
    ) -> None:
        client_with_config.app.state.candidates = [  # type: ignore[union-attr]
            _make_candidate("a.md", "b.md"),
        ]
        response = client_with_config.get("/review")
        assert response.status_code == 200
        assert "Random Target" in response.text
        assert "Select a Note" in response.text

    def test_shows_candidate_count(
        self, client_with_config: TestClient,
    ) -> None:
        client_with_config.app.state.candidates = [  # type: ignore[union-attr]
            _make_candidate("a.md", "b.md"),
            _make_candidate("a.md", "c.md"),
        ]
        response = client_with_config.get("/review")
        assert response.status_code == 200
        assert "2 candidate pairs" in response.text

    def test_shows_target_notes_in_dropdown(
        self, client_with_config: TestClient,
    ) -> None:
        client_with_config.app.state.candidates = [  # type: ignore[union-attr]
            _make_candidate("alpha.md", "beta.md"),
        ]
        response = client_with_config.get("/review")
        assert "alpha" in response.text
        assert "beta" in response.text


class TestRandomTarget:
    """Tests for GET /review/random-target."""

    def test_returns_pair_display(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {"a.md": "# A\n\nContent A", "b.md": "# B\n\nContent B"}
        _setup_review_vault(client_with_config, notes)
        client_with_config.app.state.candidates = [  # type: ignore[union-attr]
            _make_candidate("a.md", "b.md"),
        ]

        response = client_with_config.get("/review/random-target")
        assert response.status_code == 200
        assert "Content A" in response.text or "Content B" in response.text

    def test_shows_decision_buttons(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {"a.md": "# A\n\nContent A", "b.md": "# B\n\nContent B"}
        _setup_review_vault(client_with_config, notes)
        client_with_config.app.state.candidates = [  # type: ignore[union-attr]
            _make_candidate("a.md", "b.md"),
        ]

        response = client_with_config.get("/review/random-target")
        assert "Yes" in response.text
        assert "No" in response.text
        assert "Skip" in response.text

    def test_shows_explanation(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {"a.md": "# A\n\nContent A", "b.md": "# B\n\nContent B"}
        _setup_review_vault(client_with_config, notes)
        client_with_config.app.state.candidates = [  # type: ignore[union-attr]
            _make_candidate("a.md", "b.md"),
        ]

        response = client_with_config.get("/review/random-target")
        assert "RRF" in response.text or "Semantic" in response.text

    def test_returns_done_when_no_candidates(
        self, client_with_config: TestClient,
    ) -> None:
        client_with_config.app.state.candidates = []  # type: ignore[union-attr]
        response = client_with_config.get("/review/random-target")
        assert response.status_code == 200
        assert "reviewed" in response.text.lower() or "no" in response.text.lower()


class TestSelectTarget:
    """Tests for GET /review/select-target."""

    def test_shows_pair_for_selected_note(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "# A\n\nContent A",
            "b.md": "# B\n\nContent B",
            "c.md": "# C\n\nContent C",
        }
        _setup_review_vault(client_with_config, notes)
        client_with_config.app.state.candidates = [  # type: ignore[union-attr]
            _make_candidate("a.md", "b.md"),
            _make_candidate("a.md", "c.md"),
        ]

        response = client_with_config.get("/review/select-target?path=a.md")
        assert response.status_code == 200
        assert "Content A" in response.text

    def test_returns_done_for_note_with_no_candidates(
        self, client_with_config: TestClient,
    ) -> None:
        client_with_config.app.state.candidates = [  # type: ignore[union-attr]
            _make_candidate("a.md", "b.md"),
        ]
        response = client_with_config.get("/review/select-target?path=z.md")
        assert response.status_code == 200


class TestDecide:
    """Tests for POST /review/decide."""

    def test_yes_decision_removes_pair_from_candidates(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {"a.md": "# A\n\nContent A", "b.md": "# B\n\nContent B"}
        _setup_review_vault(client_with_config, notes)
        client_with_config.app.state.candidates = [  # type: ignore[union-attr]
            _make_candidate("a.md", "b.md"),
        ]

        response = client_with_config.post(
            "/review/decide",
            data={
                "target": "a.md",
                "candidate": "b.md",
                "decision": "YES",
                "skipped": "",
            },
        )
        assert response.status_code == 200
        # Candidate should be removed from app.state
        assert len(client_with_config.app.state.candidates) == 0  # type: ignore[union-attr]

    def test_no_decision_removes_pair_from_candidates(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {"a.md": "# A\n\nContent A", "b.md": "# B\n\nContent B"}
        _setup_review_vault(client_with_config, notes)
        client_with_config.app.state.candidates = [  # type: ignore[union-attr]
            _make_candidate("a.md", "b.md"),
        ]

        response = client_with_config.post(
            "/review/decide",
            data={
                "target": "a.md",
                "candidate": "b.md",
                "decision": "NO",
                "skipped": "",
            },
        )
        assert response.status_code == 200
        assert len(client_with_config.app.state.candidates) == 0  # type: ignore[union-attr]

    def test_skip_does_not_remove_pair(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "# A\n\nContent A",
            "b.md": "# B\n\nContent B",
            "c.md": "# C\n\nContent C",
        }
        _setup_review_vault(client_with_config, notes)
        client_with_config.app.state.candidates = [  # type: ignore[union-attr]
            _make_candidate("a.md", "b.md", rrf_score=0.05),
            _make_candidate("a.md", "c.md", rrf_score=0.03),
        ]

        response = client_with_config.post(
            "/review/decide",
            data={
                "target": "a.md",
                "candidate": "b.md",
                "decision": "SKIP",
                "skipped": "",
            },
        )
        assert response.status_code == 200
        # Candidate should still be in app.state
        assert len(client_with_config.app.state.candidates) == 2  # type: ignore[union-attr]

    def test_shows_next_pair_after_decision(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "# A\n\nContent A",
            "b.md": "# B\n\nContent B",
            "c.md": "# C\n\nContent C",
        }
        _setup_review_vault(client_with_config, notes)
        client_with_config.app.state.candidates = [  # type: ignore[union-attr]
            _make_candidate("a.md", "b.md", rrf_score=0.05),
            _make_candidate("a.md", "c.md", rrf_score=0.03),
        ]

        response = client_with_config.post(
            "/review/decide",
            data={
                "target": "a.md",
                "candidate": "b.md",
                "decision": "YES",
                "skipped": "",
            },
        )
        assert response.status_code == 200
        # Should show the next candidate (c.md)
        assert "Content C" in response.text

    def test_shows_target_done_when_all_reviewed(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {"a.md": "# A\n\nContent A", "b.md": "# B\n\nContent B"}
        _setup_review_vault(client_with_config, notes)
        client_with_config.app.state.candidates = [  # type: ignore[union-attr]
            _make_candidate("a.md", "b.md"),
        ]

        response = client_with_config.post(
            "/review/decide",
            data={
                "target": "a.md",
                "candidate": "b.md",
                "decision": "YES",
                "skipped": "",
            },
        )
        assert response.status_code == 200
        assert "Complete" in response.text or "reviewed" in response.text.lower()


class TestSearchPage:
    """Tests for the search page."""

    def test_search_page_renders_search_form(
        self, client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/search")
        assert response.status_code == 200
        assert 'name="q"' in response.text


class TestNavigation:
    """Tests for navigation bar updates."""

    def test_nav_contains_review_link(
        self, client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/")
        assert response.status_code == 200
        assert 'href="/review"' in response.text

    def test_nav_contains_search_link(
        self, client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/")
        assert response.status_code == 200
        assert 'href="/search"' in response.text


class TestDashboardReviewLink:
    """Tests for the review link on the dashboard."""

    def test_dashboard_shows_review_link_when_candidates_exist(
        self, client_with_config: TestClient,
    ) -> None:
        client_with_config.app.state.candidate_count = 5  # type: ignore[union-attr]
        response = client_with_config.get("/")
        assert response.status_code == 200
        assert "Review candidates" in response.text

    def test_dashboard_shows_no_review_when_zero_candidates(
        self, client_with_config: TestClient,
    ) -> None:
        client_with_config.app.state.candidate_count = 0  # type: ignore[union-attr]
        response = client_with_config.get("/")
        assert response.status_code == 200
        assert "No pairs to review" in response.text
