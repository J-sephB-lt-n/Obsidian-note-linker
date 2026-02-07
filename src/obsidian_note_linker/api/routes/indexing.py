"""Indexing routes — SSE progress stream for note indexing."""

import asyncio
import html
import logging
from collections.abc import AsyncGenerator, Generator
from typing import TypeVar

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.responses import Response, StreamingResponse

from obsidian_note_linker.infrastructure.model2vec_provider import Model2VecProvider
from obsidian_note_linker.services.candidate_service import CandidateService
from obsidian_note_linker.services.indexing_service import (
    IndexingProgress,
    IndexingResult,
    IndexingService,
)

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
    if request.app.state.is_indexing:
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
        try:
            # --- Load embedding provider (cached after first call) ---
            yield _format_sse(
                "progress",
                "<progress></progress><p>Loading embedding model...</p>",
            )

            provider = await asyncio.to_thread(
                _get_or_create_provider, request.app.state,
            )

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
            yield _format_sse(
                "progress",
                "<progress></progress>"
                "<p><small>candidates</small></p>"
                "<p>Generating candidates...</p>",
            )

            candidate_service = CandidateService(
                engine=request.app.state.db_engine,
                vault_path=config.vault_path,
            )
            candidate_count = await loop.run_in_executor(
                None, candidate_service.get_candidate_count,
            )
            request.app.state.candidate_count = candidate_count

            assert indexing_result is not None, "Indexing should have produced a result"
            yield _format_sse(
                "complete",
                _render_complete(
                    result=indexing_result,
                    candidate_count=candidate_count,
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


def _render_progress(progress: IndexingProgress) -> str:
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


def _render_complete(result: IndexingResult, candidate_count: int) -> str:
    """Render the completion summary as an HTML fragment."""
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
