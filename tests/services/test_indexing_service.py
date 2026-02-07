"""Tests for the indexing service."""

from pathlib import Path

from sqlalchemy.engine import Engine

from obsidian_note_linker.infrastructure.embedding_store import count_embeddings
from obsidian_note_linker.infrastructure.note_store import count_note_records
from obsidian_note_linker.services.indexing_service import (
    IndexingProgress,
    IndexingService,
    IndexingStatus,
)


class _FakeEmbeddingProvider:
    """Deterministic fake embedding provider for tests."""

    @property
    def model_name(self) -> str:
        return "fake-model"

    @property
    def dimension(self) -> int:
        return 3

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(i), float(i + 1), float(i + 2)] for i in range(len(texts))]


def _make_service(db_engine: Engine, vault_path: Path) -> IndexingService:
    """Helper to create an IndexingService with a fake provider."""
    return IndexingService(
        engine=db_engine,
        embedding_provider=_FakeEmbeddingProvider(),
        vault_path=vault_path,
    )


def _run_to_completion(service: IndexingService) -> list[IndexingProgress]:
    """Consume the indexing generator and return all progress events."""
    return list(service.run_indexing())


class TestGetStatus:
    """Tests for IndexingService.get_status."""

    def test_empty_vault(self, db_engine: Engine, vault_path: Path) -> None:
        service = _make_service(db_engine, vault_path)

        status = service.get_status()

        assert status == IndexingStatus(
            total_notes_in_vault=0, notes_indexed=0, notes_needing_indexing=0,
        )

    def test_unindexed_notes(self, db_engine: Engine, vault_path: Path) -> None:
        (vault_path / "a.md").write_text("Hello", encoding="utf-8")
        (vault_path / "b.md").write_text("World", encoding="utf-8")
        service = _make_service(db_engine, vault_path)

        status = service.get_status()

        assert status.total_notes_in_vault == 2
        assert status.notes_indexed == 0
        assert status.notes_needing_indexing == 2

    def test_fully_indexed_vault(self, db_engine: Engine, vault_path: Path) -> None:
        (vault_path / "note.md").write_text("Content", encoding="utf-8")
        service = _make_service(db_engine, vault_path)
        _run_to_completion(service)

        status = service.get_status()

        assert status.total_notes_in_vault == 1
        assert status.notes_indexed == 1
        assert status.notes_needing_indexing == 0

    def test_detects_changed_note(self, db_engine: Engine, vault_path: Path) -> None:
        note_file = vault_path / "note.md"
        note_file.write_text("Original", encoding="utf-8")
        service = _make_service(db_engine, vault_path)
        _run_to_completion(service)

        note_file.write_text("Modified", encoding="utf-8")
        status = service.get_status()

        assert status.notes_needing_indexing == 1


class TestRunIndexing:
    """Tests for IndexingService.run_indexing."""

    def test_yields_progress_events(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        (vault_path / "note.md").write_text("Hello", encoding="utf-8")
        service = _make_service(db_engine, vault_path)

        events = _run_to_completion(service)

        assert len(events) >= 3, "Should yield multiple progress events"
        phases = [e.phase for e in events]
        assert "scanning" in phases
        assert "complete" in phases

    def test_final_event_has_result(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        (vault_path / "note.md").write_text("Hello", encoding="utf-8")
        service = _make_service(db_engine, vault_path)

        events = _run_to_completion(service)
        final = events[-1]

        assert final.phase == "complete"
        assert final.result is not None
        assert final.result.notes_added == 1
        assert final.result.total_notes_indexed == 1

    def test_indexes_new_notes(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        (vault_path / "a.md").write_text("Alpha", encoding="utf-8")
        (vault_path / "b.md").write_text("Beta", encoding="utf-8")
        service = _make_service(db_engine, vault_path)

        events = _run_to_completion(service)
        result = events[-1].result

        assert result is not None
        assert result.notes_added == 2
        assert result.notes_unchanged == 0
        assert count_note_records(db_engine) == 2
        assert count_embeddings(db_engine) == 2

    def test_incremental_reindexing(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        (vault_path / "a.md").write_text("Alpha", encoding="utf-8")
        service = _make_service(db_engine, vault_path)
        _run_to_completion(service)

        # Add a new note and rerun
        (vault_path / "b.md").write_text("Beta", encoding="utf-8")
        events = _run_to_completion(service)
        result = events[-1].result

        assert result is not None
        assert result.notes_added == 1, "Should only add the new note"
        assert result.notes_unchanged == 1, "First note should be unchanged"
        assert result.total_notes_indexed == 2

    def test_detects_changed_content(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        note_file = vault_path / "note.md"
        note_file.write_text("Original", encoding="utf-8")
        service = _make_service(db_engine, vault_path)
        _run_to_completion(service)

        note_file.write_text("Modified", encoding="utf-8")
        events = _run_to_completion(service)
        result = events[-1].result

        assert result is not None
        assert result.notes_updated == 1
        assert result.notes_added == 0

    def test_detects_deleted_notes(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        note_file = vault_path / "note.md"
        note_file.write_text("Temporary", encoding="utf-8")
        service = _make_service(db_engine, vault_path)
        _run_to_completion(service)

        note_file.unlink()
        events = _run_to_completion(service)
        result = events[-1].result

        assert result is not None
        assert result.notes_deleted == 1
        assert result.total_notes_indexed == 0

    def test_reuses_cached_embeddings(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        (vault_path / "note.md").write_text("Content", encoding="utf-8")
        service = _make_service(db_engine, vault_path)

        # First run computes embedding
        events1 = _run_to_completion(service)
        result1 = events1[-1].result
        assert result1 is not None
        assert result1.embeddings_computed == 1
        assert result1.embeddings_cached == 0

        # Delete note record but keep embedding cache, then re-index
        # Simulate: same content re-appears → embedding reused from cache
        from obsidian_note_linker.infrastructure.note_store import delete_note_records

        delete_note_records(db_engine, relative_paths=["note.md"])

        events2 = _run_to_completion(service)
        result2 = events2[-1].result
        assert result2 is not None
        assert result2.embeddings_computed == 0, "Should reuse cached embedding"
        assert result2.embeddings_cached == 1

    def test_empty_vault_completes_successfully(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        service = _make_service(db_engine, vault_path)

        events = _run_to_completion(service)
        result = events[-1].result

        assert result is not None
        assert result.total_notes_indexed == 0
        assert result.notes_added == 0
