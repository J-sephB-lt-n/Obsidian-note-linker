"""Review routes — human-in-the-loop candidate pair review."""

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from starlette.responses import Response

from obsidian_note_linker.domain.candidate import CandidatePair
from obsidian_note_linker.services.review_service import ReviewService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/review")
async def review_page(request: Request) -> Response:
    """Render the review landing page with target selection.

    Shows target selection UI if candidates are available, or a
    message directing the user to run indexing first.
    """
    templates = request.app.state.templates
    candidates: list[CandidatePair] = _get_candidates(request)
    has_candidates = len(candidates) > 0

    context: dict[str, object] = {
        "request": request,
        "has_candidates": has_candidates,
    }

    if has_candidates:
        service = _get_review_service(request)
        targets = service.get_targets_with_candidates(candidates)
        context["total_candidates"] = len(candidates)
        context["target_count"] = len(targets)
        context["targets"] = targets

    return templates.TemplateResponse(request, "review.html", context)


@router.get("/review/random-target")
async def random_target(request: Request) -> Response:
    """HTMX partial: pick a random target and show its first candidate pair."""
    candidates = _get_candidates(request)
    service = _get_review_service(request)

    target = service.get_random_target(candidates)
    if target is None:
        return _render_no_candidates(request)

    return _render_next_pair(
        request=request,
        service=service,
        candidates=candidates,
        target=target,
        skipped_keys="",
    )


@router.get("/review/select-target")
async def select_target(request: Request) -> Response:
    """HTMX partial: show the first candidate pair for a selected target note."""
    path_str = request.query_params.get("path", "")
    if not path_str:
        return _render_no_candidates(request)

    target = Path(path_str)
    candidates = _get_candidates(request)
    service = _get_review_service(request)

    return _render_next_pair(
        request=request,
        service=service,
        candidates=candidates,
        target=target,
        skipped_keys="",
    )


@router.post("/review/decide")
async def decide(request: Request) -> Response:
    """Record a decision and show the next candidate pair.

    Handles YES/NO (persisted to DB) and SKIP (tracked in form data
    for the current target session only).
    """
    form = await request.form()
    target_str = str(form.get("target", ""))
    candidate_str = str(form.get("candidate", ""))
    decision = str(form.get("decision", ""))
    skipped_keys_str = str(form.get("skipped", ""))

    target = Path(target_str)
    candidate = Path(candidate_str)
    candidates = _get_candidates(request)
    service = _get_review_service(request)

    if decision in ("YES", "NO"):
        service.record_decision(
            note_a_path=target,
            note_b_path=candidate,
            decision=decision,
        )
        # Remove the decided pair from the in-memory candidate list
        pair_key = tuple(sorted([target, candidate]))
        request.app.state.candidates = [
            c for c in candidates if c.pair_key != pair_key
        ]
        candidates = request.app.state.candidates

    elif decision == "SKIP":
        # Add to skipped keys for this target session
        pair_key_str = _encode_pair_key(target, candidate)
        if skipped_keys_str:
            skipped_keys_str = f"{skipped_keys_str},{pair_key_str}"
        else:
            skipped_keys_str = pair_key_str

    return _render_next_pair(
        request=request,
        service=service,
        candidates=candidates,
        target=target,
        skipped_keys=skipped_keys_str,
    )


# --- Helpers ------------------------------------------------------------------


def _get_candidates(request: Request) -> list[CandidatePair]:
    """Retrieve the current candidate list from app state."""
    candidates = getattr(request.app.state, "candidates", None)
    if candidates is None:
        return []
    return candidates


def _get_review_service(request: Request) -> ReviewService:
    """Create a ReviewService from app state."""
    config = request.app.state.config_service.load_config()
    assert config is not None, "Vault must be configured for review"
    return ReviewService(
        engine=request.app.state.db_engine,
        vault_path=config.vault_path,
    )


def _parse_skipped_keys(skipped_str: str) -> set[tuple[Path, Path]]:
    """Parse a comma-separated string of skipped pair keys.

    Each pair key is encoded as ``path_a|path_b`` (canonically sorted).
    """
    if not skipped_str:
        return set()

    keys: set[tuple[Path, Path]] = set()
    for item in skipped_str.split(","):
        item = item.strip()
        if "|" in item:
            parts = item.split("|", maxsplit=1)
            keys.add((Path(parts[0]), Path(parts[1])))
    return keys


def _encode_pair_key(path_a: Path, path_b: Path) -> str:
    """Encode a pair key as a string for form data transport."""
    sorted_paths = sorted([path_a, path_b])
    return f"{sorted_paths[0]}|{sorted_paths[1]}"


def _render_next_pair(
    request: Request,
    service: ReviewService,
    candidates: list[CandidatePair],
    target: Path,
    skipped_keys: str,
) -> Response:
    """Render the next candidate pair or target-done partial."""
    templates = request.app.state.templates
    skipped = _parse_skipped_keys(skipped_keys)

    target_candidates = service.get_candidates_for_target(
        candidates=candidates,
        target=target,
        skipped_pair_keys=skipped,
    )

    if not target_candidates:
        # No more candidates for this target
        remaining = len(candidates)
        target_title = target.stem
        return templates.TemplateResponse(
            request,
            "_review_target_done.html",
            {
                "request": request,
                "target_title": target_title,
                "remaining_candidates": remaining,
            },
        )

    # Show the top candidate
    pair = target_candidates[0]
    candidate_index = 1
    candidates_total = len(target_candidates)

    # Determine which note in the pair is the target and which is the candidate
    if pair.note_a_path == target:
        other_path = pair.note_b_path
    else:
        other_path = pair.note_a_path

    target_title, target_html = service.read_and_render_note(target)
    candidate_title, candidate_html = service.read_and_render_note(other_path)

    return templates.TemplateResponse(
        request,
        "_review_pair.html",
        {
            "request": request,
            "target_title": target_title,
            "target_path": str(target),
            "target_html": target_html,
            "candidate_title": candidate_title,
            "candidate_path": str(other_path),
            "candidate_html": candidate_html,
            "explanation": pair.explanation,
            "candidate_index": candidate_index,
            "candidates_total": candidates_total,
            "skipped_keys": skipped_keys,
        },
    )


def _render_no_candidates(request: Request) -> Response:
    """Render a message when no candidates are available."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "_review_target_done.html",
        {
            "request": request,
            "target_title": "Unknown",
            "remaining_candidates": 0,
        },
    )
