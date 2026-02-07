"""Indexing service — orchestrates vault scanning, diffing, and embedding.

Provides incremental indexing: only new and changed notes are embedded,
and previously computed embeddings are reused from cache.
"""

import logging
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine

from obsidian_note_linker.domain.embedding_provider import EmbeddingProvider
from obsidian_note_linker.domain.markdown_stripper import prepare_note_for_embedding
from obsidian_note_linker.domain.note import Note
from obsidian_note_linker.infrastructure.embedding_store import (
    get_cached_embeddings,
    save_embeddings,
)
from obsidian_note_linker.infrastructure.note_store import (
    count_note_records,
    delete_note_records,
    get_all_note_records,
    upsert_note_record,
)
from obsidian_note_linker.infrastructure.vault_scanner import scan_vault

logger = logging.getLogger(__name__)

EMBEDDING_BATCH_SIZE = 50


@dataclass(frozen=True)
class IndexingStatus:
    """Current state of the note index for dashboard display."""

    total_notes_in_vault: int
    notes_indexed: int
    notes_needing_indexing: int


@dataclass(frozen=True)
class IndexingResult:
    """Summary of a completed indexing run."""

    notes_added: int
    notes_updated: int
    notes_deleted: int
    notes_unchanged: int
    embeddings_computed: int
    embeddings_cached: int
    total_notes_indexed: int


@dataclass(frozen=True)
class IndexingProgress:
    """Progress update yielded during indexing.

    When ``result`` is not None the indexing run has completed.
    """

    phase: str
    current: int
    total: int
    message: str
    result: IndexingResult | None = None


def get_indexing_status(engine: Engine, vault_path: Path) -> IndexingStatus:
    """Get the current indexing status without performing any indexing.

    Scans the vault and compares with stored records to determine
    how many notes need (re-)indexing.  Does not require an embedding
    provider, making it safe to call from the dashboard.

    Args:
        engine: SQLAlchemy engine.
        vault_path: Absolute path to the Obsidian vault.

    Returns:
        IndexingStatus with vault and index counts.
    """
    vault_notes = scan_vault(vault_path)
    stored_records = get_all_note_records(engine)
    stored_by_path: dict[str, str] = {
        r.relative_path: r.content_hash for r in stored_records
    }

    needs_indexing = sum(
        1
        for note in vault_notes
        if stored_by_path.get(str(note.relative_path)) != note.content_hash
    )

    return IndexingStatus(
        total_notes_in_vault=len(vault_notes),
        notes_indexed=len(stored_records),
        notes_needing_indexing=needs_indexing,
    )


class IndexingService:
    """Orchestrates incremental note indexing and embedding.

    Args:
        engine: SQLAlchemy engine for database access.
        embedding_provider: Provider for computing text embeddings.
        vault_path: Absolute path to the Obsidian vault.
    """

    def __init__(
        self,
        engine: Engine,
        embedding_provider: EmbeddingProvider,
        vault_path: Path,
    ) -> None:
        self._engine = engine
        self._provider = embedding_provider
        self._vault_path = vault_path

    def get_status(self) -> IndexingStatus:
        """Get the current indexing status (delegates to module-level function)."""
        return get_indexing_status(self._engine, self._vault_path)

    def run_indexing(self) -> Generator[IndexingProgress, None, None]:
        """Run incremental indexing, yielding progress updates.

        Phases:
            1. **scanning** — read all ``.md`` files from the vault
            2. **diffing** — compare with stored note records
            3. **embedding** — compute embeddings for new/changed notes
            4. **storing** — update note records in the database
            5. **complete** — final progress with ``result`` populated

        Yields:
            IndexingProgress updates.  The final yield has ``result`` set.
        """
        yield IndexingProgress(
            phase="scanning", current=0, total=0,
            message="Scanning vault for notes...",
        )
        vault_notes = scan_vault(self._vault_path)

        # --- Diff with stored state ---
        stored_records = get_all_note_records(self._engine)
        stored_by_path: dict[str, str] = {
            r.relative_path: r.content_hash for r in stored_records
        }
        vault_paths = {str(n.relative_path) for n in vault_notes}

        new_notes, changed_notes, unchanged_notes = _diff_notes(
            vault_notes=vault_notes, stored_by_path=stored_by_path,
        )
        deleted_paths = [p for p in stored_by_path if p not in vault_paths]

        notes_to_embed = new_notes + changed_notes
        total_to_embed = len(notes_to_embed)

        yield IndexingProgress(
            phase="diffing", current=0, total=total_to_embed,
            message=(
                f"Found {len(new_notes)} new, {len(changed_notes)} changed, "
                f"{len(deleted_paths)} deleted, {len(unchanged_notes)} unchanged"
            ),
        )

        # --- Check embedding cache ---
        hashes_needed = [n.content_hash for n in notes_to_embed]
        cached = get_cached_embeddings(self._engine, content_hashes=hashes_needed)
        uncached_notes = [n for n in notes_to_embed if n.content_hash not in cached]
        embeddings_cached = total_to_embed - len(uncached_notes)

        logger.info(
            "Embedding cache: %d hit(s), %d miss(es)",
            embeddings_cached, len(uncached_notes),
        )

        # --- Compute embeddings in batches ---
        embeddings_computed = 0
        for batch_start in range(0, len(uncached_notes), EMBEDDING_BATCH_SIZE):
            batch = uncached_notes[batch_start : batch_start + EMBEDDING_BATCH_SIZE]
            batch_end = batch_start + len(batch)

            yield IndexingProgress(
                phase="embedding",
                current=batch_start,
                total=len(uncached_notes),
                message=f"Embedding notes {batch_start + 1}–{batch_end} of {len(uncached_notes)}...",
            )

            texts = [
                prepare_note_for_embedding(
                    title=note.relative_path.stem,
                    content=note.content,
                )
                for note in batch
            ]
            batch_embeddings = self._provider.embed(texts)
            batch_hashes = [n.content_hash for n in batch]

            save_embeddings(
                self._engine,
                content_hashes=batch_hashes,
                embeddings=batch_embeddings,
                model_name=self._provider.model_name,
                dimension=self._provider.dimension,
            )
            embeddings_computed += len(batch)

        # --- Update note records ---
        yield IndexingProgress(
            phase="storing", current=0, total=len(notes_to_embed),
            message="Updating note index...",
        )

        for note in notes_to_embed:
            upsert_note_record(
                self._engine,
                relative_path=str(note.relative_path),
                content_hash=note.content_hash,
            )

        if deleted_paths:
            delete_note_records(self._engine, relative_paths=deleted_paths)

        total_indexed = count_note_records(self._engine)

        result = IndexingResult(
            notes_added=len(new_notes),
            notes_updated=len(changed_notes),
            notes_deleted=len(deleted_paths),
            notes_unchanged=len(unchanged_notes),
            embeddings_computed=embeddings_computed,
            embeddings_cached=embeddings_cached,
            total_notes_indexed=total_indexed,
        )

        logger.info(
            "Indexing complete: +%d /%d -%d (=%d total), "
            "%d embeddings computed, %d cached",
            result.notes_added, result.notes_updated, result.notes_deleted,
            result.total_notes_indexed,
            result.embeddings_computed, result.embeddings_cached,
        )

        yield IndexingProgress(
            phase="complete",
            current=total_to_embed,
            total=total_to_embed,
            message=f"Indexing complete: {total_indexed} notes indexed",
            result=result,
        )


def _diff_notes(
    vault_notes: list[Note],
    stored_by_path: dict[str, str],
) -> tuple[list[Note], list[Note], list[Note]]:
    """Classify vault notes as new, changed, or unchanged.

    Args:
        vault_notes: Notes currently in the vault.
        stored_by_path: Mapping of relative_path → content_hash from DB.

    Returns:
        Tuple of (new_notes, changed_notes, unchanged_notes).
    """
    new: list[Note] = []
    changed: list[Note] = []
    unchanged: list[Note] = []

    for note in vault_notes:
        path_str = str(note.relative_path)
        stored_hash = stored_by_path.get(path_str)
        if stored_hash is None:
            new.append(note)
        elif stored_hash != note.content_hash:
            changed.append(note)
        else:
            unchanged.append(note)

    return new, changed, unchanged
