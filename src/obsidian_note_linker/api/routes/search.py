"""Search routes — document search with FTS, semantic, and hybrid modes."""

import logging
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from starlette.responses import Response

from obsidian_note_linker.domain.search import SearchMode
from obsidian_note_linker.infrastructure.markdown_renderer import render_markdown
from obsidian_note_linker.services.search_service import SearchService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/search")
async def search_page(request: Request) -> Response:
    """Render the search page with query input and mode selector.

    Serves as the entry point for document search.  Results are
    loaded dynamically via HTMX into the ``#search-results`` div.
    """
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "search.html", {
        "request": request,
        "query": "",
        "mode": "hybrid",
    })


@router.get("/search/results")
def search_results(
    request: Request,
    q: str = Query(default=""),
    mode: str = Query(default="hybrid"),
) -> Response:
    """Return search results as an HTML fragment for HTMX.

    Called by HTMX when the user submits the search form.  Performs
    the search and returns a partial template with ranked results.

    Args:
        q: Free-text search query.
        mode: Search mode string (``fts``, ``semantic``, or ``hybrid``).
    """
    templates = request.app.state.templates
    engine = request.app.state.db_engine

    # Parse mode
    try:
        search_mode = SearchMode(mode)
    except ValueError:
        search_mode = SearchMode.HYBRID

    # Build service
    config = request.app.state.config_service.load_config()
    assert config is not None, "Vault must be configured before searching"

    embedding_provider = getattr(request.app.state, "embedding_provider", None)
    service = SearchService(
        engine=engine,
        vault_path=config.vault_path,
        embedding_provider=embedding_provider,
    )

    # Check readiness
    warning = service.check_readiness(mode=search_mode)
    if warning:
        return templates.TemplateResponse(request, "_search_results.html", {
            "request": request,
            "results": [],
            "warning": warning,
        })

    # Handle empty query
    if not q or not q.strip():
        return HTMLResponse("")

    # Perform search
    results = service.search(query=q, mode=search_mode)

    if not results:
        return templates.TemplateResponse(request, "_search_results.html", {
            "request": request,
            "results": [],
        })

    return templates.TemplateResponse(request, "_search_results.html", {
        "request": request,
        "results": results,
    })


@router.get("/search/note")
def search_note_view(
    request: Request,
    path: str = Query(...),
) -> Response:
    """Return the full rendered content of a note for inline expansion.

    Called by HTMX when the user clicks "View full note" on a search
    result.  Reads the note file, renders it with mistune, and returns
    an HTML fragment.

    Args:
        path: Relative path of the note within the vault.
    """
    templates = request.app.state.templates

    config = request.app.state.config_service.load_config()
    assert config is not None, "Vault must be configured"

    decoded_path = unquote(path)
    note_path = config.vault_path / decoded_path

    if not note_path.is_file():
        return HTMLResponse(
            "<p>Note not found.</p>",
            status_code=404,
        )

    content = note_path.read_text(encoding="utf-8")
    rendered_content = render_markdown(content)
    title = Path(decoded_path).stem.replace("-", " ").replace("_", " ").title()

    return templates.TemplateResponse(request, "_search_note.html", {
        "request": request,
        "title": title,
        "relative_path": decoded_path,
        "rendered_content": rendered_content,
    })
