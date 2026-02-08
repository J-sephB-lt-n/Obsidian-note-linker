"""Tests for apply routes — link application UI."""

from fastapi.testclient import TestClient

from obsidian_note_linker.domain.note import compute_content_hash
from obsidian_note_linker.infrastructure.decision_store import (
    get_pending_approved_pairs,
    save_decision,
)
from obsidian_note_linker.infrastructure.note_store import upsert_note_record


def _setup_apply_vault(
    client: TestClient,
    notes: dict[str, str],
    approve_pairs: list[tuple[str, str]] | None = None,
) -> None:
    """Create note files, DB records, and optional YES decisions."""
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

    if approve_pairs:
        for note_a, note_b in approve_pairs:
            save_decision(
                engine=engine,
                note_a_path=note_a,
                note_b_path=note_b,
                decision="YES",
                note_a_hash=compute_content_hash(notes[note_a]),
                note_b_hash=compute_content_hash(notes[note_b]),
            )


class TestApplyPage:
    """Tests for GET /apply."""

    def test_shows_apply_page_when_configured(
        self, client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/apply")
        assert response.status_code == 200
        assert "Apply" in response.text

    def test_shows_no_pending_message_when_empty(
        self, client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/apply")
        assert response.status_code == 200
        assert "No Pending" in response.text or "no pending" in response.text.lower()

    def test_shows_pending_count_when_pairs_exist(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {"a.md": "# A\n", "b.md": "# B\n"}
        _setup_apply_vault(
            client_with_config, notes,
            approve_pairs=[("a.md", "b.md")],
        )
        response = client_with_config.get("/apply")
        assert response.status_code == 200
        assert "1" in response.text

    def test_shows_start_button_when_pairs_pending(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {"a.md": "# A\n", "b.md": "# B\n"}
        _setup_apply_vault(
            client_with_config, notes,
            approve_pairs=[("a.md", "b.md")],
        )
        response = client_with_config.get("/apply")
        assert response.status_code == 200
        assert "Begin" in response.text or "Start" in response.text


class TestApplyNextPair:
    """Tests for GET /apply/next-pair."""

    def test_shows_diff_preview(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {"a.md": "# A\n\nContent A\n", "b.md": "# B\n\nContent B\n"}
        _setup_apply_vault(
            client_with_config, notes,
            approve_pairs=[("a.md", "b.md")],
        )
        response = client_with_config.get("/apply/next-pair")
        assert response.status_code == 200
        assert "## Related" in response.text or "Related" in response.text

    def test_shows_both_note_titles(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {"alpha.md": "# Alpha\n", "beta.md": "# Beta\n"}
        _setup_apply_vault(
            client_with_config, notes,
            approve_pairs=[("alpha.md", "beta.md")],
        )
        response = client_with_config.get("/apply/next-pair")
        assert response.status_code == 200
        assert "alpha" in response.text
        assert "beta" in response.text

    def test_shows_done_when_no_pairs(
        self, client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/apply/next-pair")
        assert response.status_code == 200
        assert "complete" in response.text.lower() or "done" in response.text.lower() or "No" in response.text


class TestApplyConfirm:
    """Tests for POST /apply/confirm."""

    def test_applies_links_and_shows_next(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "# A\n\nContent A\n",
            "b.md": "# B\n\nContent B\n",
            "c.md": "# C\n\nContent C\n",
        }
        _setup_apply_vault(
            client_with_config, notes,
            approve_pairs=[("a.md", "b.md"), ("a.md", "c.md")],
        )
        engine = client_with_config.app.state.db_engine  # type: ignore[union-attr]
        pairs = get_pending_approved_pairs(engine=engine)
        pair_id = pairs[0].id

        response = client_with_config.post(
            "/apply/confirm",
            data={"pair_id": str(pair_id)},
        )
        assert response.status_code == 200

        # One pair should have been applied
        remaining = get_pending_approved_pairs(engine=engine)
        assert len(remaining) == 1

    def test_writes_links_to_disk(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {"a.md": "# A\n\nContent A\n", "b.md": "# B\n\nContent B\n"}
        _setup_apply_vault(
            client_with_config, notes,
            approve_pairs=[("a.md", "b.md")],
        )
        engine = client_with_config.app.state.db_engine  # type: ignore[union-attr]
        pairs = get_pending_approved_pairs(engine=engine)
        pair_id = pairs[0].id

        client_with_config.post(
            "/apply/confirm",
            data={"pair_id": str(pair_id)},
        )

        config = client_with_config.app.state.config_service.load_config()  # type: ignore[union-attr]
        content_a = (config.vault_path / "a.md").read_text(encoding="utf-8")
        content_b = (config.vault_path / "b.md").read_text(encoding="utf-8")
        assert "b.md" in content_a
        assert "a.md" in content_b

    def test_shows_done_after_last_pair(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {"a.md": "# A\n", "b.md": "# B\n"}
        _setup_apply_vault(
            client_with_config, notes,
            approve_pairs=[("a.md", "b.md")],
        )
        engine = client_with_config.app.state.db_engine  # type: ignore[union-attr]
        pairs = get_pending_approved_pairs(engine=engine)
        pair_id = pairs[0].id

        response = client_with_config.post(
            "/apply/confirm",
            data={"pair_id": str(pair_id)},
        )
        assert response.status_code == 200
        assert "complete" in response.text.lower() or "All" in response.text


class TestApplySkip:
    """Tests for POST /apply/skip."""

    def test_skips_pair_and_shows_next(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "# A\n",
            "b.md": "# B\n",
            "c.md": "# C\n",
        }
        _setup_apply_vault(
            client_with_config, notes,
            approve_pairs=[("a.md", "b.md"), ("a.md", "c.md")],
        )
        engine = client_with_config.app.state.db_engine  # type: ignore[union-attr]
        pairs = get_pending_approved_pairs(engine=engine)
        pair_id = pairs[0].id

        response = client_with_config.post(
            "/apply/skip",
            data={"pair_id": str(pair_id)},
        )
        assert response.status_code == 200

        # Pair should NOT have been applied (still pending)
        remaining = get_pending_approved_pairs(engine=engine)
        assert len(remaining) == 2


class TestNavigation:
    """Tests for navigation bar updates."""

    def test_nav_contains_apply_link(
        self, client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/")
        assert response.status_code == 200
        assert 'href="/apply"' in response.text


class TestDashboardPendingLinks:
    """Tests for the Pending Links card on the dashboard."""

    def test_dashboard_shows_pending_links_count(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {"a.md": "# A\n", "b.md": "# B\n"}
        _setup_apply_vault(
            client_with_config, notes,
            approve_pairs=[("a.md", "b.md")],
        )
        response = client_with_config.get("/")
        assert response.status_code == 200
        assert "Pending Links" in response.text
        assert "1" in response.text

    def test_dashboard_shows_zero_pending(
        self, client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/")
        assert response.status_code == 200
        assert "Pending Links" in response.text

    def test_dashboard_pending_links_to_apply(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {"a.md": "# A\n", "b.md": "# B\n"}
        _setup_apply_vault(
            client_with_config, notes,
            approve_pairs=[("a.md", "b.md")],
        )
        response = client_with_config.get("/")
        assert response.status_code == 200
        assert 'href="/apply"' in response.text
