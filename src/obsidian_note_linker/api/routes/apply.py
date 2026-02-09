"""Apply routes — safe bidirectional link creation with diff preview."""

import logging

from fastapi import APIRouter, Request
from starlette.responses import Response

from obsidian_note_linker.infrastructure.decision_store import (
    get_pending_approved_pairs,
)
from obsidian_note_linker.infrastructure.models import DecisionRecord
from obsidian_note_linker.services.link_service import LinkService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/apply")
def apply_page(request: Request) -> Response:
    """Render the apply landing page with pending pair count.

    Uses a synchronous handler so FastAPI runs it in a thread pool.
    """
    logger.info("Apply page requested")
    templates = request.app.state.templates
    engine = request.app.state.db_engine

    pending_count = 0
    if engine is not None:
        pending = get_pending_approved_pairs(engine=engine)
        pending_count = len(pending)

    return templates.TemplateResponse(
        request,
        "apply.html",
        {
            "pending_count": pending_count,
        },
    )


@router.get("/apply/next-pair")
def next_pair(request: Request) -> Response:
    """HTMX partial: show the diff preview for the next pending pair."""
    service = _get_link_service(request)
    pending = service.get_pending_pairs()

    if not pending:
        return _render_done(request)

    decision = pending[0]
    try:
        preview = service.preview_pair(decision)
    except FileNotFoundError:
        logger.warning(
            "Note file missing for pair (%s, %s), skipping",
            decision.note_a_path, decision.note_b_path,
        )
        return _render_error(
            request,
            f"Note file missing for pair ({decision.note_a_path}, "
            f"{decision.note_b_path}). Please re-index.",
        )

    templates = request.app.state.templates
    remaining = len(pending)

    return templates.TemplateResponse(
        request,
        "_apply_pair.html",
        {
            "request": request,
            "preview": preview,
            "pair_id": decision.id,
            "remaining": remaining,
            "pair_index": 1,
        },
    )


@router.post("/apply/confirm")
async def confirm_pair(request: Request) -> Response:
    """Apply links for a confirmed pair, then show the next one."""
    form = await request.form()
    pair_id = int(str(form.get("pair_id", "0")))
    logger.info("Confirm apply for pair_id=%d", pair_id)

    service = _get_link_service(request)
    decision = _find_decision(service, pair_id)

    if decision is not None:
        try:
            service.apply_pair(decision)
        except FileNotFoundError:
            logger.exception("Failed to apply pair %d", pair_id)
            return _render_error(
                request,
                f"Note file missing for pair ({decision.note_a_path}, "
                f"{decision.note_b_path}). Please re-index.",
            )

    return _render_next_or_done(request, service)


@router.post("/apply/skip")
async def skip_pair(request: Request) -> Response:
    """Skip a pair without applying and show the next one."""
    form = await request.form()
    pair_id = int(str(form.get("pair_id", "0")))
    logger.info("Skip apply for pair_id=%d", pair_id)

    service = _get_link_service(request)

    # Find remaining pairs excluding the skipped one
    pending = service.get_pending_pairs()
    remaining = [p for p in pending if p.id != pair_id]

    if not remaining:
        return _render_done(request)

    next_decision = remaining[0]
    try:
        preview = service.preview_pair(next_decision)
    except FileNotFoundError:
        return _render_error(request, "Note file missing. Please re-index.")

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "_apply_pair.html",
        {
            "request": request,
            "preview": preview,
            "pair_id": next_decision.id,
            "remaining": len(remaining),
            "pair_index": 1,
        },
    )


# --- Helpers ------------------------------------------------------------------


def _get_link_service(request: Request) -> LinkService:
    """Create a LinkService from app state."""
    config = request.app.state.config_service.load_config()
    assert config is not None, "Vault must be configured for link application"
    return LinkService(
        engine=request.app.state.db_engine,
        vault_path=config.vault_path,
    )


def _find_decision(
    service: LinkService,
    pair_id: int,
) -> DecisionRecord | None:
    """Find a specific decision by ID from pending pairs."""
    for decision in service.get_pending_pairs():
        if decision.id == pair_id:
            return decision
    return None


def _render_next_or_done(request: Request, service: LinkService) -> Response:
    """Show the next pending pair or the completion message."""
    pending = service.get_pending_pairs()
    if not pending:
        return _render_done(request)

    next_decision = pending[0]
    try:
        preview = service.preview_pair(next_decision)
    except FileNotFoundError:
        return _render_error(request, "Note file missing. Please re-index.")

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "_apply_pair.html",
        {
            "request": request,
            "preview": preview,
            "pair_id": next_decision.id,
            "remaining": len(pending),
            "pair_index": 1,
        },
    )


def _render_done(request: Request) -> Response:
    """Render the all-done partial."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "_apply_done.html",
        {"request": request},
    )


def _render_error(request: Request, message: str) -> Response:
    """Render an error message partial."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "_apply_done.html",
        {"request": request, "error": message},
    )
