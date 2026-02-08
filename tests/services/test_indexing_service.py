"""Tests for the indexing service."""

from pathlib import Path

from sqlalchemy.engine import Engine

from obsidian_note_linker.infrastructure.embedding_store import count_embeddings
from obsidian_note_linker.infrastructure.note_store import (
    count_note_records,
    delete_note_records,
)
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


class TestProgressReporting:
    """Tests for accurate progress reporting during indexing phases."""

    def test_scanning_phase_yields_determinate_progress(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        """Scanning phase should yield start (0/1) and completion (1/1)."""
        (vault_path / "note.md").write_text("Hello", encoding="utf-8")
        service = _make_service(db_engine, vault_path)

        events = _run_to_completion(service)
        scanning = [e for e in events if e.phase == "scanning"]

        assert len(scanning) == 2, "Scanning should yield start and done events"
        assert scanning[0].current == 0
        assert scanning[0].total == 1
        assert scanning[1].current == 1
        assert scanning[1].total == 1

    def test_diffing_phase_yields_determinate_progress(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        """Diffing phase should yield start (0/1) and completion (1/1)."""
        (vault_path / "note.md").write_text("Hello", encoding="utf-8")
        service = _make_service(db_engine, vault_path)

        events = _run_to_completion(service)
        diffing = [e for e in events if e.phase == "diffing"]

        assert len(diffing) == 2, "Diffing should yield start and done events"
        assert diffing[0].current == 0
        assert diffing[0].total == 1
        assert diffing[1].current == 1
        assert diffing[1].total == 1

    def test_embedding_progress_advances_after_each_batch(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        """Embedding progress current should advance after each batch completes."""
        for i in range(3):
            (vault_path / f"note{i}.md").write_text(
                f"Content {i}", encoding="utf-8",
            )
        service = _make_service(db_engine, vault_path)

        events = _run_to_completion(service)
        embedding = [e for e in events if e.phase == "embedding"]

        assert len(embedding) >= 1, "Should yield at least one embedding event"
        # Total should be the number of notes to embed
        assert embedding[0].total == 3
        # Final embedding event should show all notes completed
        assert embedding[-1].current == embedding[-1].total

    def test_embedding_progress_accounts_for_cached_embeddings(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        """Cached embeddings should be reflected in progress immediately."""
        (vault_path / "note.md").write_text("Content", encoding="utf-8")
        service = _make_service(db_engine, vault_path)
        _run_to_completion(service)

        # Delete note record but keep embedding in cache
        delete_note_records(db_engine, relative_paths=["note.md"])

        events = _run_to_completion(service)
        embedding = [e for e in events if e.phase == "embedding"]

        assert len(embedding) >= 1, "Should yield embedding events even when cached"
        # With 1 note and its embedding cached, progress should reach total
        last = embedding[-1]
        assert last.current == last.total == 1, (
            "Cached embedding should be reflected in progress"
        )

    def test_embedding_all_cached_reaches_completion(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        """When all embeddings are cached, progress should show full completion."""
        (vault_path / "a.md").write_text("Alpha", encoding="utf-8")
        (vault_path / "b.md").write_text("Beta", encoding="utf-8")
        service = _make_service(db_engine, vault_path)
        _run_to_completion(service)

        # Delete note records but keep embeddings cached
        delete_note_records(db_engine, relative_paths=["a.md", "b.md"])

        events = _run_to_completion(service)
        embedding = [e for e in events if e.phase == "embedding"]

        assert len(embedding) >= 1
        last = embedding[-1]
        assert last.current == last.total == 2

    def test_storing_progress_advances_per_note(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        """Storing phase should yield progress advancing through each note."""
        (vault_path / "a.md").write_text("Alpha", encoding="utf-8")
        (vault_path / "b.md").write_text("Beta", encoding="utf-8")
        service = _make_service(db_engine, vault_path)

        events = _run_to_completion(service)
        storing = [e for e in events if e.phase == "storing"]

        assert len(storing) >= 2, "Should yield multiple storing events"
        # Should advance from 0 to total
        assert storing[0].current == 0
        assert storing[-1].current == storing[-1].total
        assert storing[-1].total == 2

    def test_storing_includes_deletions_in_total(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        """Deleted notes should be included in the storing phase total."""
        (vault_path / "a.md").write_text("Alpha", encoding="utf-8")
        (vault_path / "b.md").write_text("Beta", encoding="utf-8")
        service = _make_service(db_engine, vault_path)
        _run_to_completion(service)

        # Delete one note file so it becomes a deletion
        (vault_path / "b.md").unlink()
        events = _run_to_completion(service)
        storing = [e for e in events if e.phase == "storing"]

        # Storing should account for the deletion
        assert len(storing) >= 1
        last = storing[-1]
        assert last.current == last.total, "Should reach completion"
        assert last.total >= 1, "Should include at least the deletion"

    def test_no_embedding_phase_when_nothing_to_embed(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        """When all notes are up to date, embedding phase should be skipped."""
        (vault_path / "note.md").write_text("Content", encoding="utf-8")
        service = _make_service(db_engine, vault_path)
        _run_to_completion(service)

        events = _run_to_completion(service)
        embedding = [e for e in events if e.phase == "embedding"]

        assert len(embedding) == 0, "No embedding events when nothing to embed"

    def test_no_storing_phase_when_nothing_to_store(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        """When all notes are up to date, storing phase should be skipped."""
        (vault_path / "note.md").write_text("Content", encoding="utf-8")
        service = _make_service(db_engine, vault_path)
        _run_to_completion(service)

        events = _run_to_completion(service)
        storing = [e for e in events if e.phase == "storing"]

        assert len(storing) == 0, "No storing events when nothing to store"

    def test_all_phases_reach_completion(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        """Every phase's final event should have current == total."""
        for i in range(3):
            (vault_path / f"note{i}.md").write_text(
                f"Unique content {i}", encoding="utf-8",
            )
        service = _make_service(db_engine, vault_path)

        events = _run_to_completion(service)

        # Group events by phase and check each phase reaches completion
        phases: dict[str, list[IndexingProgress]] = {}
        for e in events:
            if e.phase != "complete":
                phases.setdefault(e.phase, []).append(e)

        for phase_name, phase_events in phases.items():
            last = phase_events[-1]
            assert last.current == last.total, (
                f"Phase '{phase_name}' did not reach completion: "
                f"{last.current}/{last.total}"
            )

    def test_progress_values_are_monotonically_non_decreasing(
        self, db_engine: Engine, vault_path: Path,
    ) -> None:
        """Within each phase, current should never decrease."""
        for i in range(3):
            (vault_path / f"note{i}.md").write_text(
                f"Unique content {i}", encoding="utf-8",
            )
        service = _make_service(db_engine, vault_path)

        events = _run_to_completion(service)

        phases: dict[str, list[IndexingProgress]] = {}
        for e in events:
            if e.phase != "complete":
                phases.setdefault(e.phase, []).append(e)

        for phase_name, phase_events in phases.items():
            for i in range(1, len(phase_events)):
                assert phase_events[i].current >= phase_events[i - 1].current, (
                    f"Phase '{phase_name}' progress decreased at event {i}: "
                    f"{phase_events[i - 1].current} -> {phase_events[i].current}"
                )
