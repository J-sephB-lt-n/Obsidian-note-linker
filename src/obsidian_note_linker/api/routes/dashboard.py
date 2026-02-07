"""Dashboard route — main landing page with indexing status."""

import logging

from fastapi import APIRouter, Request
from starlette.responses import Response

from obsidian_note_linker.services.indexing_service import (
    IndexingStatus,
    get_indexing_status,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
def dashboard(request: Request) -> Response:
    """Render the dashboard page with indexing status.

    Uses a synchronous handler so FastAPI runs it in a thread pool,
    avoiding blocking the event loop during vault scanning.
    """
    config = request.app.state.config_service.load_config()
    templates = request.app.state.templates
    engine = request.app.state.db_engine

    status: IndexingStatus | None = None
    if config and engine:
        try:
            status = get_indexing_status(
                engine=engine, vault_path=config.vault_path,
            )
        except Exception:
            logger.exception("Failed to get indexing status")

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "vault_path": str(config.vault_path) if config else None,
            "status": status,
            "is_indexing": getattr(request.app.state, "is_indexing", False),
        },
    )
