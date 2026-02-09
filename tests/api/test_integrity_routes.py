"""Tests for integrity routes — incomplete link detection and resolution UI."""

from pathlib import Path

from fastapi.testclient import TestClient

from obsidian_note_linker.domain.related_section_parser import IncompleteLink
from obsidian_note_linker.infrastructure.audit_store import get_audit_log


def _setup_integrity_vault(
    client: TestClient,
    notes: dict[str, str],
    incomplete_links: list[IncompleteLink] | None = None,
) -> None:
    """Create note files on disk and set up incomplete links in app state."""
    config = client.app.state.config_service.load_config()  # type: ignore[union-attr]
    vault_path = config.vault_path

    for rel_path, content in notes.items():
        full_path = vault_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")

    if incomplete_links is not None:
        client.app.state.incomplete_links = incomplete_links  # type: ignore[union-attr]
        client.app.state.incomplete_link_count = len(incomplete_links)  # type: ignore[union-attr]


class TestIntegrityPage:
    """Tests for GET /integrity."""

    def test_shows_page_when_configured(
        self, client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/integrity")
        assert response.status_code == 200
        assert "Integrity" in response.text

    def test_shows_indexing_required_when_no_detection(
        self, client_with_config: TestClient,
    ) -> None:
        """Before indexing, incomplete_link_count is None → prompt to index."""
        response = client_with_config.get("/integrity")
        assert response.status_code == 200
        assert "Indexing Required" in response.text or "indexing" in response.text.lower()

    def test_shows_no_issues_when_zero(
        self, client_with_config: TestClient,
    ) -> None:
        client_with_config.app.state.incomplete_link_count = 0  # type: ignore[union-attr]
        client_with_config.app.state.incomplete_links = []  # type: ignore[union-attr]

        response = client_with_config.get("/integrity")
        assert response.status_code == 200
        assert "Complete" in response.text or "No incomplete" in response.text

    def test_shows_count_when_issues_exist(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "## Related\n\n- [B](<b.md>)\n",
            "b.md": "# B\n",
        }
        _setup_integrity_vault(
            client_with_config, notes,
            incomplete_links=[
                IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md")),
            ],
        )
        response = client_with_config.get("/integrity")
        assert response.status_code == 200
        assert "1" in response.text

    def test_shows_begin_button_when_issues_exist(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "## Related\n\n- [B](<b.md>)\n",
            "b.md": "# B\n",
        }
        _setup_integrity_vault(
            client_with_config, notes,
            incomplete_links=[
                IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md")),
            ],
        )
        response = client_with_config.get("/integrity")
        assert response.status_code == 200
        assert "Begin" in response.text


class TestIntegrityNextPair:
    """Tests for GET /integrity/next-pair."""

    def test_shows_both_notes_side_by_side(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "alpha.md": "# Alpha\n\n## Related\n\n- [Beta](<beta.md>)\n",
            "beta.md": "# Beta\n\nSome content.\n",
        }
        _setup_integrity_vault(
            client_with_config, notes,
            incomplete_links=[
                IncompleteLink(source_path=Path("alpha.md"), target_path=Path("beta.md")),
            ],
        )
        response = client_with_config.get("/integrity/next-pair")
        assert response.status_code == 200
        assert "alpha" in response.text
        assert "beta" in response.text

    def test_shows_complete_and_remove_buttons(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "## Related\n\n- [B](<b.md>)\n",
            "b.md": "# B\n",
        }
        _setup_integrity_vault(
            client_with_config, notes,
            incomplete_links=[
                IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md")),
            ],
        )
        response = client_with_config.get("/integrity/next-pair")
        assert response.status_code == 200
        assert "Complete" in response.text
        assert "Remove" in response.text

    def test_shows_done_when_no_links(
        self, client_with_config: TestClient,
    ) -> None:
        client_with_config.app.state.incomplete_links = []  # type: ignore[union-attr]
        client_with_config.app.state.incomplete_link_count = 0  # type: ignore[union-attr]

        response = client_with_config.get("/integrity/next-pair")
        assert response.status_code == 200
        assert "Resolved" in response.text or "resolved" in response.text.lower() or "complete" in response.text.lower()

    def test_shows_remaining_count(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "## Related\n\n- [B](<b.md>)\n- [C](<c.md>)\n",
            "b.md": "# B\n",
            "c.md": "# C\n",
        }
        _setup_integrity_vault(
            client_with_config, notes,
            incomplete_links=[
                IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md")),
                IncompleteLink(source_path=Path("a.md"), target_path=Path("c.md")),
            ],
        )
        response = client_with_config.get("/integrity/next-pair")
        assert response.status_code == 200
        assert "2" in response.text


class TestIntegrityResolve:
    """Tests for POST /integrity/resolve."""

    def test_shows_diff_preview_for_complete(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "## Related\n\n- [B](<b.md>)\n",
            "b.md": "# B\n\nContent.\n",
        }
        _setup_integrity_vault(
            client_with_config, notes,
            incomplete_links=[
                IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md")),
            ],
        )
        response = client_with_config.post(
            "/integrity/resolve",
            data={
                "source_path": "a.md",
                "target_path": "b.md",
                "action": "complete",
            },
        )
        assert response.status_code == 200
        assert "a.md" in response.text
        assert "Confirm" in response.text

    def test_shows_diff_preview_for_remove(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "# A\n\n## Related\n\n- [B](<b.md>)\n",
            "b.md": "# B\n",
        }
        _setup_integrity_vault(
            client_with_config, notes,
            incomplete_links=[
                IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md")),
            ],
        )
        response = client_with_config.post(
            "/integrity/resolve",
            data={
                "source_path": "a.md",
                "target_path": "b.md",
                "action": "remove",
            },
        )
        assert response.status_code == 200
        assert "b.md" in response.text
        assert "Confirm" in response.text

    def test_diff_shows_addition_for_complete(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "## Related\n\n- [B](<b.md>)\n",
            "b.md": "# B\n\nContent.\n",
        }
        _setup_integrity_vault(
            client_with_config, notes,
            incomplete_links=[
                IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md")),
            ],
        )
        response = client_with_config.post(
            "/integrity/resolve",
            data={
                "source_path": "a.md",
                "target_path": "b.md",
                "action": "complete",
            },
        )
        assert response.status_code == 200
        assert "## Related" in response.text


class TestIntegrityConfirm:
    """Tests for POST /integrity/confirm."""

    def test_complete_adds_link_to_disk(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "## Related\n\n- [B](<b.md>)\n",
            "b.md": "# B\n\nContent.\n",
        }
        _setup_integrity_vault(
            client_with_config, notes,
            incomplete_links=[
                IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md")),
            ],
        )
        response = client_with_config.post(
            "/integrity/confirm",
            data={
                "source_path": "a.md",
                "target_path": "b.md",
                "action": "complete",
            },
        )
        assert response.status_code == 200

        config = client_with_config.app.state.config_service.load_config()  # type: ignore[union-attr]
        content_b = (config.vault_path / "b.md").read_text(encoding="utf-8")
        assert "a.md" in content_b

    def test_remove_deletes_link_from_disk(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "# A\n\n## Related\n\n- [B](<b.md>)\n- [C](<c.md>)\n",
            "b.md": "# B\n",
        }
        _setup_integrity_vault(
            client_with_config, notes,
            incomplete_links=[
                IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md")),
            ],
        )
        response = client_with_config.post(
            "/integrity/confirm",
            data={
                "source_path": "a.md",
                "target_path": "b.md",
                "action": "remove",
            },
        )
        assert response.status_code == 200

        config = client_with_config.app.state.config_service.load_config()  # type: ignore[union-attr]
        content_a = (config.vault_path / "a.md").read_text(encoding="utf-8")
        assert "b.md" not in content_a
        assert "c.md" in content_a

    def test_removes_resolved_link_from_state(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "## Related\n\n- [B](<b.md>)\n",
            "b.md": "# B\n",
        }
        _setup_integrity_vault(
            client_with_config, notes,
            incomplete_links=[
                IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md")),
            ],
        )
        client_with_config.post(
            "/integrity/confirm",
            data={
                "source_path": "a.md",
                "target_path": "b.md",
                "action": "complete",
            },
        )

        remaining = client_with_config.app.state.incomplete_links  # type: ignore[union-attr]
        assert len(remaining) == 0
        assert client_with_config.app.state.incomplete_link_count == 0  # type: ignore[union-attr]

    def test_shows_done_after_last_link(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "## Related\n\n- [B](<b.md>)\n",
            "b.md": "# B\n",
        }
        _setup_integrity_vault(
            client_with_config, notes,
            incomplete_links=[
                IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md")),
            ],
        )
        response = client_with_config.post(
            "/integrity/confirm",
            data={
                "source_path": "a.md",
                "target_path": "b.md",
                "action": "complete",
            },
        )
        assert response.status_code == 200
        assert "Resolved" in response.text or "resolved" in response.text.lower() or "complete" in response.text.lower()

    def test_creates_audit_entry_for_complete(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "## Related\n\n- [B](<b.md>)\n",
            "b.md": "# B\n",
        }
        _setup_integrity_vault(
            client_with_config, notes,
            incomplete_links=[
                IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md")),
            ],
        )
        client_with_config.post(
            "/integrity/confirm",
            data={
                "source_path": "a.md",
                "target_path": "b.md",
                "action": "complete",
            },
        )

        engine = client_with_config.app.state.db_engine  # type: ignore[union-attr]
        audit = get_audit_log(engine=engine, note_path="b.md")
        assert len(audit) == 1
        assert audit[0].action == "COMPLETE_LINK"

    def test_creates_audit_entry_for_remove(
        self, client_with_config: TestClient,
    ) -> None:
        notes = {
            "a.md": "# A\n\n## Related\n\n- [B](<b.md>)\n",
            "b.md": "# B\n",
        }
        _setup_integrity_vault(
            client_with_config, notes,
            incomplete_links=[
                IncompleteLink(source_path=Path("a.md"), target_path=Path("b.md")),
            ],
        )
        client_with_config.post(
            "/integrity/confirm",
            data={
                "source_path": "a.md",
                "target_path": "b.md",
                "action": "remove",
            },
        )

        engine = client_with_config.app.state.db_engine  # type: ignore[union-attr]
        audit = get_audit_log(engine=engine, note_path="a.md")
        assert len(audit) == 1
        assert audit[0].action == "REMOVE_LINK"


class TestNavigation:
    """Tests for navigation bar updates."""

    def test_nav_contains_integrity_link(
        self, client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/")
        assert response.status_code == 200
        assert 'href="/integrity"' in response.text


class TestDashboardIncompleteLinks:
    """Tests for the Incomplete Links card on the dashboard."""

    def test_dashboard_shows_incomplete_links_card(
        self, client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/")
        assert response.status_code == 200
        assert "Incomplete Links" in response.text

    def test_dashboard_shows_dash_before_indexing(
        self, client_with_config: TestClient,
    ) -> None:
        """Before indexing, incomplete_link_count is None → greyed dash."""
        response = client_with_config.get("/")
        assert response.status_code == 200
        assert "Run indexing to detect" in response.text

    def test_dashboard_shows_count_after_indexing(
        self, client_with_config: TestClient,
    ) -> None:
        client_with_config.app.state.incomplete_link_count = 3  # type: ignore[union-attr]

        response = client_with_config.get("/")
        assert response.status_code == 200
        assert "3" in response.text
        assert "Resolve incomplete links" in response.text

    def test_dashboard_shows_zero_incomplete(
        self, client_with_config: TestClient,
    ) -> None:
        client_with_config.app.state.incomplete_link_count = 0  # type: ignore[union-attr]

        response = client_with_config.get("/")
        assert response.status_code == 200
        assert "All links are complete" in response.text

    def test_dashboard_links_to_integrity_page(
        self, client_with_config: TestClient,
    ) -> None:
        client_with_config.app.state.incomplete_link_count = 2  # type: ignore[union-attr]

        response = client_with_config.get("/")
        assert response.status_code == 200
        assert 'href="/integrity"' in response.text
