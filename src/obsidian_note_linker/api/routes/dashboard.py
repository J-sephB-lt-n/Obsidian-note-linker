"""Dashboard route — main landing page."""

from fastapi import APIRouter, Request
from starlette.responses import Response

router = APIRouter()


@router.get("/")
async def dashboard(request: Request) -> Response:
    """Render the dashboard page with status overview placeholders."""
    config = request.app.state.config_service.load_config()
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"vault_path": str(config.vault_path) if config else None},
    )
