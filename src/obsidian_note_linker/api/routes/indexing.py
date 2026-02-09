"""Indexing routes — SSE progress stream for note indexing."""

import asyncio
import html
import logging
from collections.abc import AsyncGenerator, Generator
from typing import TypeVar

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.responses import Response, StreamingResponse

from obsidian_note_linker.domain.progress import ProgressUpdate
from obsidian_note_linker.infrastructure.model2vec_provider import Model2VecProvider
from obsidian_note_linker.services.candidate_service import CandidateService
from obsidian_note_linker.services.indexing_service import (
    IndexingProgress,
    IndexingResult,
    IndexingService,
)
from obsidian_note_linker.services.integrity_service import detect_incomplete_links

_T = TypeVar("_T")
_EXHAUSTED = object()

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/indexing")


@router.get("/start")
async def indexing_start(request: Request) -> Response:
    """Return an HTML fragment with an SSE-connected progress display.

    Called by HTMX when the user clicks "Index Now".  The returned
    fragment replaces the button area and opens an SSE connection
    to ``/indexing/stream``.
    """
    logger.info("Indexing start requested")
    if request.app.state.is_indexing:
        logger.warning("Indexing already in progress, rejecting request")
        return HTMLResponse(
            '<article><p>Indexing is already in progress.</p></article>',
            status_code=409,
        )

    fragment = (
        '<div hx-ext="sse" sse-connect="/indexing/stream" sse-close="complete">'
        "  <article>"
        "    <header><strong>Indexing in Progress</strong></header>"
        '    <div id="index-progress" sse-swap="progress">'
        "      <progress></progress>"
        "      <p>Connecting...</p>"
        "    </div>"
        '    <div sse-swap="complete"></div>'
        "  </article>"
        "</div>"
    )
    return HTMLResponse(fragment)


@router.get("/stream")
async def indexing_stream(request: Request) -> StreamingResponse:
    """SSE endpoint that runs indexing and streams progress events.

    Lazily loads the embedding model on first call, then runs incremental
    indexing.  Each progress update is sent as an SSE event.  The final
    event (``complete``) includes a summary and closes the connection.
    """
    if request.app.state.is_indexing:
        return StreamingResponse(
            _error_event("Indexing already in progress."),
            media_type="text/event-stream",
        )

    config = request.app.state.config_service.load_config()
    assert config is not None, "Vault must be configured before indexing"

    async def generate() -> AsyncGenerator[str, None]:
        request.app.state.is_indexing = True
        logger.info("Indexing stream started")
        try:
            # --- Load embedding provider (cached after first call) ---
            yield _format_sse(
                "progress",
                "<progress></progress><p>Loading embedding model...</p>",
            )

            logger.info("Loading embedding model")
            provider = await asyncio.to_thread(
                _get_or_create_provider, request.app.state,
            )
            logger.info("Embedding model ready")

            # --- Run indexing ---
            service = IndexingService(
                engine=request.app.state.db_engine,
                embedding_provider=provider,
                vault_path=config.vault_path,
            )
            gen = service.run_indexing()
            loop = asyncio.get_event_loop()

            indexing_result: IndexingResult | None = None
            while True:
                value = await loop.run_in_executor(
                    None, _safe_next, gen,
                )
                if value is _EXHAUSTED:
                    break

                progress: IndexingProgress = value  # type: ignore[assignment]
                if progress.result is not None:
                    indexing_result = progress.result
                else:
                    yield _format_sse("progress", _render_progress(progress))

            # --- Generate candidates after indexing ---
            logger.info("Starting candidate generation")
            candidate_service = CandidateService(
                engine=request.app.state.db_engine,
                vault_path=config.vault_path,
            )
            cand_gen = candidate_service.generate_candidates_with_progress()

            while True:
                cand_value = await loop.run_in_executor(
                    None, _safe_next, cand_gen,
                )
                if cand_value is _EXHAUSTED:
                    break
                cand_progress: ProgressUpdate = cand_value  # type: ignore[assignment]
                yield _format_sse(
                    "progress", _render_progress(cand_progress),
                )

            candidates = candidate_service.get_candidate_count()
            request.app.state.candidates = candidate_service._candidates
            candidate_count = candidates
            request.app.state.candidate_count = candidate_count
            logger.info("Candidate generation complete: %d candidates", candidate_count)

            # --- Detect incomplete links after candidate generation ---
            logger.info("Starting incomplete link detection")
            yield _format_sse(
                "progress",
                _render_progress(ProgressUpdate(
                    phase="integrity",
                    current=0,
                    total=1,
                    message="Checking link integrity...",
                )),
            )

            incomplete_links = await asyncio.to_thread(
                detect_incomplete_links, config.vault_path,
            )
            request.app.state.incomplete_links = incomplete_links
            request.app.state.incomplete_link_count = len(incomplete_links)
            logger.info("Incomplete link detection complete: %d found", len(incomplete_links))

            yield _format_sse(
                "progress",
                _render_progress(ProgressUpdate(
                    phase="integrity",
                    current=1,
                    total=1,
                    message=f"Found {len(incomplete_links)} incomplete link{'s' if len(incomplete_links) != 1 else ''}",
                )),
            )

            assert indexing_result is not None, "Indexing should have produced a result"
            yield _format_sse(
                "complete",
                _render_complete(
                    result=indexing_result,
                    candidate_count=candidate_count,
                    incomplete_link_count=len(incomplete_links),
                ),
            )

        except Exception:
            logger.exception("Indexing failed")
            yield _format_sse(
                "complete",
                '<article><header><strong>Indexing Failed</strong></header>'
                "<p>An error occurred during indexing. Check the logs.</p>"
                '<footer><a href="/" role="button">Back to Dashboard</a></footer>'
                "</article>",
            )
        finally:
            request.app.state.is_indexing = False
            logger.info("Indexing stream finished")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _safe_next(gen: Generator[_T, None, None]) -> _T | object:
    """Advance a generator, returning ``_EXHAUSTED`` instead of raising.

    ``StopIteration`` cannot propagate through ``run_in_executor``
    (Python wraps it in ``RuntimeError``), so this helper converts it
    to a sentinel value.
    """
    try:
        return next(gen)
    except StopIteration:
        return _EXHAUSTED


def _get_or_create_provider(app_state: object) -> Model2VecProvider:
    """Get the cached embedding provider, creating it on first call."""
    if getattr(app_state, "embedding_provider", None) is None:
        app_state.embedding_provider = Model2VecProvider()  # type: ignore[union-attr]
    return app_state.embedding_provider  # type: ignore[union-attr]


def _format_sse(event: str, data: str) -> str:
    """Format an SSE event string."""
    # SSE spec: multi-line data uses separate "data:" prefixes
    lines = data.replace("\n", " ").strip()
    return f"event: {event}\ndata: {lines}\n\n"


def _render_progress(progress: ProgressUpdate) -> str:
    """Render a progress update as an HTML fragment."""
    phase = html.escape(progress.phase)
    message = html.escape(progress.message)

    if progress.total > 0:
        pct = min(progress.current / progress.total, 1.0)
        return (
            f'<progress value="{pct:.2f}" max="1"></progress>'
            f"<p><small>{phase}</small></p>"
            f"<p>{message}</p>"
        )
    return f"<progress></progress><p><small>{phase}</small></p><p>{message}</p>"


def _render_complete(
    result: IndexingResult,
    candidate_count: int,
    incomplete_link_count: int = 0,
) -> str:
    """Render the completion summary as an HTML fragment."""
    integrity_line = f"<p>Incomplete links: {incomplete_link_count}</p>"
    return (
        "<article>"
        "<header><strong>Indexing Complete</strong></header>"
        f"<p>Added: {result.notes_added} &bull; "
        f"Updated: {result.notes_updated} &bull; "
        f"Deleted: {result.notes_deleted} &bull; "
        f"Unchanged: {result.notes_unchanged}</p>"
        f"<p>Embeddings computed: {result.embeddings_computed} &bull; "
        f"Cached: {result.embeddings_cached}</p>"
        f"<p><strong>Total notes indexed: {result.total_notes_indexed}</strong></p>"
        f"<p>Candidates found: {candidate_count}</p>"
        f"{integrity_line}"
        '<footer><a href="/" role="button">Back to Dashboard</a></footer>'
        "</article>"
    )


async def _error_event(message: str) -> AsyncGenerator[str, None]:
    """Yield a single SSE error event."""
    yield _format_sse(
        "complete",
        f"<article><p>{html.escape(message)}</p>"
        '<footer><a href="/" role="button">Back to Dashboard</a></footer>'
        "</article>",
    )
