"""Search routes — placeholder for document search (Slice 7)."""

from fastapi import APIRouter, Request
from starlette.responses import Response

router = APIRouter()


@router.get("/search")
async def search_page(request: Request) -> Response:
    """Render the search page placeholder.

    Full document search (FTS, semantic, hybrid) will be
    implemented in Slice 7.
    """
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "search.html", {"request": request})
