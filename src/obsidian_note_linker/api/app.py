"""FastAPI application factory."""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from obsidian_note_linker.infrastructure.logging_setup import setup_logging
from obsidian_note_linker.services.config_service import ConfigService
from obsidian_note_linker.services.vault_init import initialize_vault_state

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Paths that are accessible even when no vault is configured.
_SETUP_PATHS = frozenset({"/setup", "/setup/save"})


def create_app(config_path: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config_path: Path to the config JSON file.  Defaults to
                     ``~/.config/obsidian-linker/config.json``.

    Returns:
        Configured FastAPI application instance.
    """
    # Avoid circular import — routes import at function scope is intentional
    # because settings.py references initialize_vault_state from vault_init
    # (not from this module), so there is no true circular dependency.
    from obsidian_note_linker.api.routes import dashboard, indexing, settings  # noqa: E402

    app = FastAPI(title="Obsidian Note Linker")

    # Shared state
    app.state.config_service = ConfigService(config_path=config_path)
    app.state.templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.state.db_engine = None
    app.state.embedding_provider = None
    app.state.is_indexing = False
    app.state.candidate_count = None

    # Load existing config and initialise vault state
    config = app.state.config_service.load_config()
    if config is not None:
        app.state.db_engine = initialize_vault_state(config=config)
    else:
        # Console-only logging until vault is configured
        setup_logging()

    # --- Middleware -----------------------------------------------------------

    @app.middleware("http")
    async def redirect_if_unconfigured(
        request: Request,
        call_next: object,
    ) -> RedirectResponse:
        """Redirect to /setup if no vault is configured."""
        if (
            request.url.path not in _SETUP_PATHS
            and not app.state.config_service.is_configured()
        ):
            return RedirectResponse(url="/setup", status_code=303)
        return await call_next(request)  # type: ignore[misc]

    # --- Routes ---------------------------------------------------------------

    app.include_router(dashboard.router)
    app.include_router(settings.router)
    app.include_router(indexing.router)

    logger.info("Application created")
    return app
