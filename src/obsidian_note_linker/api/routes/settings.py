"""Settings and setup routes — vault configuration."""

import logging
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from starlette.responses import Response

from obsidian_note_linker.services.vault_init import initialize_vault_state

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/setup")
async def setup_page(request: Request) -> Response:
    """Render the first-run vault setup page."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "setup.html",
        {"error": None},
    )


@router.post("/setup/save")
async def setup_save(
    request: Request,
    vault_path: str = Form(...),
) -> Response:
    """Save the vault path from the setup form and initialise vault state."""
    templates = request.app.state.templates
    config_service = request.app.state.config_service

    try:
        config = config_service.save_vault_path(vault_path=Path(vault_path))
        request.app.state.db_engine = initialize_vault_state(config=config)
        return RedirectResponse(url="/", status_code=303)
    except ValueError as exc:
        logger.warning("Invalid vault path submitted: %s — %s", vault_path, exc)
        return templates.TemplateResponse(
            request,
            "setup.html",
            {"error": str(exc)},
            status_code=400,
        )


@router.get("/settings")
async def settings_page(request: Request) -> Response:
    """Render the settings page showing the current vault path."""
    config = request.app.state.config_service.load_config()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "vault_path": str(config.vault_path) if config else "",
            "error": None,
            "success": False,
        },
    )


@router.post("/settings/save")
async def settings_save(
    request: Request,
    vault_path: str = Form(...),
) -> Response:
    """Update the vault path from the settings form."""
    templates = request.app.state.templates
    config_service = request.app.state.config_service

    try:
        config = config_service.save_vault_path(vault_path=Path(vault_path))
        request.app.state.db_engine = initialize_vault_state(config=config)
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "vault_path": str(config.vault_path),
                "error": None,
                "success": True,
            },
        )
    except ValueError as exc:
        logger.warning("Invalid vault path in settings: %s — %s", vault_path, exc)
        return templates.TemplateResponse(
            request,
            "settings.html",
            {
                "vault_path": vault_path,
                "error": str(exc),
                "success": False,
            },
            status_code=400,
        )
