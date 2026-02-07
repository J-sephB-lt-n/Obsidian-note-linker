"""Tests for API routes."""

from pathlib import Path

from fastapi.testclient import TestClient


class TestSetupRedirect:
    """Tests for the middleware that redirects unconfigured apps to /setup."""

    def test_root_redirects_to_setup_when_unconfigured(
        self,
        client_no_config: TestClient,
    ) -> None:
        response = client_no_config.get("/")

        assert response.status_code == 303
        assert response.headers["location"] == "/setup"

    def test_settings_redirects_to_setup_when_unconfigured(
        self,
        client_no_config: TestClient,
    ) -> None:
        response = client_no_config.get("/settings")

        assert response.status_code == 303
        assert response.headers["location"] == "/setup"


class TestSetupPage:
    """Tests for the setup page."""

    def test_get_setup_page(self, client_no_config: TestClient) -> None:
        response = client_no_config.get("/setup")

        assert response.status_code == 200
        assert "vault" in response.text.lower()

    def test_setup_page_contains_form(self, client_no_config: TestClient) -> None:
        response = client_no_config.get("/setup")

        assert '<form method="post"' in response.text
        assert 'name="vault_path"' in response.text


class TestSetupSave:
    """Tests for saving vault path from setup form."""

    def test_save_valid_vault_path_redirects_to_dashboard(
        self,
        client_no_config: TestClient,
        tmp_path: Path,
    ) -> None:
        vault = tmp_path / "test_vault"
        vault.mkdir()

        response = client_no_config.post(
            "/setup/save",
            data={"vault_path": str(vault)},
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/"

    def test_save_nonexistent_path_returns_error(
        self,
        client_no_config: TestClient,
    ) -> None:
        response = client_no_config.post(
            "/setup/save",
            data={"vault_path": "/nonexistent/path"},
        )

        assert response.status_code == 400
        assert "does not exist" in response.text


class TestDashboard:
    """Tests for the dashboard page."""

    def test_shows_dashboard_when_configured(
        self,
        client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/")

        assert response.status_code == 200
        assert "Dashboard" in response.text

    def test_dashboard_shows_vault_path(
        self,
        client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/")

        assert response.status_code == 200
        assert "vault" in response.text.lower()


    def test_dashboard_shows_greyed_candidates_before_indexing(
        self,
        client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/")

        assert response.status_code == 200
        assert "Run indexing to generate candidates" in response.text

    def test_dashboard_shows_candidate_count_after_indexing(
        self,
        client_with_config: TestClient,
    ) -> None:
        # Simulate indexing having been run
        client_with_config.app.state.candidate_count = 42  # type: ignore[union-attr]
        response = client_with_config.get("/")

        assert response.status_code == 200
        assert "42" in response.text
        assert "Pairs to review" in response.text


class TestSettingsPage:
    """Tests for the settings page."""

    def test_shows_settings_when_configured(
        self,
        client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/settings")

        assert response.status_code == 200
        assert "Settings" in response.text

    def test_settings_shows_current_vault_path(
        self,
        client_with_config: TestClient,
    ) -> None:
        response = client_with_config.get("/settings")

        assert response.status_code == 200
        assert 'value="' in response.text


class TestSettingsSave:
    """Tests for saving settings."""

    def test_save_new_vault_path_shows_success(
        self,
        client_with_config: TestClient,
        tmp_path: Path,
    ) -> None:
        new_vault = tmp_path / "new_vault"
        new_vault.mkdir()

        response = client_with_config.post(
            "/settings/save",
            data={"vault_path": str(new_vault)},
        )

        assert response.status_code == 200
        assert "updated successfully" in response.text

    def test_save_invalid_path_returns_error(
        self,
        client_with_config: TestClient,
    ) -> None:
        response = client_with_config.post(
            "/settings/save",
            data={"vault_path": "/nonexistent/path"},
        )

        assert response.status_code == 400
        assert "does not exist" in response.text
