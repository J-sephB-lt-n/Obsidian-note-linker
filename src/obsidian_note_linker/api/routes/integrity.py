"""Integrity routes — detect and resolve incomplete bidirectional links.

Provides a pair-by-pair resolution workflow where the user can choose
to complete (add missing reverse link) or remove (delete the one-way
link) each incomplete link, with a diff preview before confirmation.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from starlette.responses import Response

from obsidian_note_linker.domain.related_section_parser import IncompleteLink
from obsidian_note_linker.infrastructure.markdown_renderer import render_markdown
from obsidian_note_linker.services.integrity_service import IntegrityService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/integrity")
def integrity_page(request: Request) -> Response:
    """Render the integrity landing page with incomplete link count.

    Shows count from ``app.state.incomplete_link_count``, or prompts
    the user to run indexing if detection hasn't been performed yet.
    """
    logger.info("Integrity page requested")
    templates = request.app.state.templates

    incomplete_link_count: int | None = getattr(
        request.app.state, "incomplete_link_count", None,
    )

    return templates.TemplateResponse(
        request,
        "integrity.html",
        {"incomplete_link_count": incomplete_link_count},
    )


@router.get("/integrity/next-pair")
def next_pair(request: Request) -> Response:
    """HTMX partial: show both notes side-by-side for the next incomplete link."""
    incomplete_links = _get_incomplete_links(request)

    if not incomplete_links:
        return _render_done(request)

    link = incomplete_links[0]
    service = _get_integrity_service(request)

    try:
        source_content = service._read_note(link.source_path)
        target_content = service._read_note(link.target_path)
    except FileNotFoundError:
        logger.warning(
            "Note file missing for incomplete link (%s → %s)",
            link.source_path, link.target_path,
        )
        return _render_error(
            request,
            f"Note file missing for ({link.source_path} → {link.target_path}). "
            f"Please re-index.",
        )

    source_html = render_markdown(source_content)
    target_html = render_markdown(target_content)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "_integrity_pair.html",
        {
            "source_title": link.source_path.stem,
            "target_title": link.target_path.stem,
            "source_path": str(link.source_path),
            "target_path": str(link.target_path),
            "source_html": source_html,
            "target_html": target_html,
            "remaining": len(incomplete_links),
        },
    )


@router.post("/integrity/resolve")
async def resolve(request: Request) -> Response:
    """HTMX partial: show the diff preview for the chosen resolution action."""
    form = await request.form()
    source_path = Path(str(form.get("source_path", "")))
    target_path = Path(str(form.get("target_path", "")))
    action = str(form.get("action", ""))

    assert action in ("complete", "remove"), f"Invalid action: {action!r}"
    logger.info(
        "Integrity resolve: action=%s, source=%s, target=%s",
        action, source_path, target_path,
    )

    service = _get_integrity_service(request)

    try:
        if action == "complete":
            preview = service.preview_complete(
                source_path=source_path, target_path=target_path,
            )
        else:
            preview = service.preview_remove(
                source_path=source_path, target_path=target_path,
            )
    except FileNotFoundError:
        return _render_error(request, "Note file missing. Please re-index.")

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "_integrity_preview.html",
        {
            "source_path": str(source_path),
            "target_path": str(target_path),
            "source_title": source_path.stem,
            "target_title": target_path.stem,
            "action": action,
            "diff": preview.diff,
            "modified_note_path": str(preview.modified_note_path),
            "modified_note_title": preview.modified_note_path.stem,
        },
    )


@router.post("/integrity/confirm")
async def confirm(request: Request) -> Response:
    """Apply the resolution and show the next incomplete link or completion."""
    form = await request.form()
    source_path = Path(str(form.get("source_path", "")))
    target_path = Path(str(form.get("target_path", "")))
    action = str(form.get("action", ""))

    assert action in ("complete", "remove"), f"Invalid action: {action!r}"
    logger.info(
        "Integrity confirm: action=%s, source=%s, target=%s",
        action, source_path, target_path,
    )

    service = _get_integrity_service(request)

    try:
        if action == "complete":
            service.apply_complete(
                source_path=source_path, target_path=target_path,
            )
        else:
            service.apply_remove(
                source_path=source_path, target_path=target_path,
            )
    except FileNotFoundError:
        logger.exception("Failed to resolve incomplete link")
        return _render_error(
            request,
            f"Note file missing for ({source_path} → {target_path}). "
            f"Please re-index.",
        )

    # Remove the resolved link from the in-memory list
    incomplete_links = _get_incomplete_links(request)
    resolved = IncompleteLink(source_path=source_path, target_path=target_path)
    request.app.state.incomplete_links = [
        il for il in incomplete_links if il != resolved
    ]
    request.app.state.incomplete_link_count = len(
        request.app.state.incomplete_links,
    )

    # Show next pair or done
    if not request.app.state.incomplete_links:
        return _render_done(request)

    # Redirect to next-pair logic
    return next_pair(request)


# --- Helpers ------------------------------------------------------------------


def _get_incomplete_links(request: Request) -> list[IncompleteLink]:
    """Retrieve the current incomplete links list from app state."""
    links = getattr(request.app.state, "incomplete_links", None)
    if links is None:
        return []
    return links


def _get_integrity_service(request: Request) -> IntegrityService:
    """Create an IntegrityService from app state."""
    config = request.app.state.config_service.load_config()
    assert config is not None, "Vault must be configured for integrity checks"
    return IntegrityService(
        engine=request.app.state.db_engine,
        vault_path=config.vault_path,
    )


def _render_done(request: Request) -> Response:
    """Render the all-resolved partial."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "_integrity_done.html",
        {"request": request},
    )


def _render_error(request: Request, message: str) -> Response:
    """Render an error message partial."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "_integrity_done.html",
        {"request": request, "error": message},
    )
