"""Tests for the candidate generation service."""

from pathlib import Path

from sqlalchemy.engine import Engine

from obsidian_note_linker.infrastructure.decision_store import save_decision
from obsidian_note_linker.infrastructure.embedding_store import save_embeddings
from obsidian_note_linker.infrastructure.note_store import upsert_note_record
from obsidian_note_linker.services.candidate_service import CandidateService


def _setup_indexed_vault(
    vault_path: Path,
    db_engine: Engine,
    notes: dict[str, str],
    embeddings: dict[str, list[float]],
) -> None:
    """Helper: create note files, store records, and save embeddings."""
    from obsidian_note_linker.domain.note import compute_content_hash

    for rel_path, content in notes.items():
        full_path = vault_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

        content_hash = compute_content_hash(content)
        upsert_note_record(
            engine=db_engine,
            relative_path=rel_path,
            content_hash=content_hash,
        )

    # Save embeddings keyed by content hash
    hashes = []
    emb_vectors = []
    for rel_path, content in notes.items():
        content_hash = compute_content_hash(content)
        if content_hash in embeddings or rel_path in embeddings:
            # Allow lookup by either path or hash
            emb = embeddings.get(rel_path) or embeddings.get(content_hash)
            if emb is not None:
                hashes.append(content_hash)
                emb_vectors.append(emb)

    if hashes:
        save_embeddings(
            engine=db_engine,
            content_hashes=hashes,
            embeddings=emb_vectors,
            model_name="test-model",
            dimension=len(emb_vectors[0]),
        )


class TestCandidateServiceGenerate:
    """Tests for candidate generation."""

    def test_generates_candidates_for_related_notes(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        """Two notes with similar embeddings should produce a candidate pair."""
        notes = {
            "a.md": "# Alpha\n\nMachine learning and neural networks.",
            "b.md": "# Beta\n\nDeep learning and neural networks.",
        }
        # Similar embeddings
        embeddings = {
            "a.md": [0.9, 0.1, 0.0],
            "b.md": [0.85, 0.15, 0.0],
        }
        _setup_indexed_vault(vault_path, db_engine, notes, embeddings)

        service = CandidateService(engine=db_engine, vault_path=vault_path)
        candidates = service.generate_candidates()

        assert len(candidates) >= 1
        # Check the pair exists (in some order)
        assert any(
            {c.note_a_path, c.note_b_path} == {Path("a.md"), Path("b.md")}
            for c in candidates
        )

    def test_returns_empty_for_single_note(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        """A single note cannot form any pairs."""
        notes = {"only.md": "# Only Note\n\nSome content."}
        embeddings = {"only.md": [1.0, 0.0]}
        _setup_indexed_vault(vault_path, db_engine, notes, embeddings)

        service = CandidateService(engine=db_engine, vault_path=vault_path)
        candidates = service.generate_candidates()

        assert candidates == []

    def test_returns_empty_when_no_notes_indexed(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        service = CandidateService(engine=db_engine, vault_path=vault_path)
        candidates = service.generate_candidates()
        assert candidates == []

    def test_candidates_sorted_by_rrf_score_descending(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        notes = {
            "a.md": "# A\n\nalpha beta gamma",
            "b.md": "# B\n\nalpha beta delta",
            "c.md": "# C\n\nepsilon zeta eta",
        }
        # a and b are very similar; c is different
        embeddings = {
            "a.md": [0.9, 0.1],
            "b.md": [0.85, 0.15],
            "c.md": [0.1, 0.9],
        }
        _setup_indexed_vault(vault_path, db_engine, notes, embeddings)

        service = CandidateService(engine=db_engine, vault_path=vault_path)
        candidates = service.generate_candidates()

        assert len(candidates) >= 2
        for i in range(len(candidates) - 1):
            assert candidates[i].rrf_score >= candidates[i + 1].rrf_score, (
                "Candidates should be sorted by RRF score descending"
            )

    def test_excludes_already_linked_bidirectional_pairs(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        """Pairs with bidirectional links in ## Related are excluded."""
        notes = {
            "a.md": (
                "# A\n\nalpha content\n\n"
                "## Related\n\n"
                "- [B](<b.md>)\n"
            ),
            "b.md": (
                "# B\n\nalpha content\n\n"
                "## Related\n\n"
                "- [A](<a.md>)\n"
            ),
            "c.md": "# C\n\nalpha content",
        }
        embeddings = {
            "a.md": [0.9, 0.1],
            "b.md": [0.85, 0.15],
            "c.md": [0.8, 0.2],
        }
        _setup_indexed_vault(vault_path, db_engine, notes, embeddings)

        service = CandidateService(engine=db_engine, vault_path=vault_path)
        candidates = service.generate_candidates()

        # a<->b should be excluded (bidirectionally linked)
        for c in candidates:
            assert not ({c.note_a_path, c.note_b_path} == {Path("a.md"), Path("b.md")}), (
                "Already-linked pair (a, b) should be excluded"
            )

    def test_excludes_previously_decided_pairs(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        """Pairs with valid YES/NO decisions are excluded."""
        from obsidian_note_linker.domain.note import compute_content_hash

        notes = {
            "a.md": "# A\n\nalpha content about AI",
            "b.md": "# B\n\nalpha content about AI models",
            "c.md": "# C\n\nalpha content about AI systems",
        }
        embeddings = {
            "a.md": [0.9, 0.1],
            "b.md": [0.85, 0.15],
            "c.md": [0.8, 0.2],
        }
        _setup_indexed_vault(vault_path, db_engine, notes, embeddings)

        # Record a decision for (a, b)
        save_decision(
            engine=db_engine,
            note_a_path="a.md",
            note_b_path="b.md",
            decision="NO",
            note_a_hash=compute_content_hash(notes["a.md"]),
            note_b_hash=compute_content_hash(notes["b.md"]),
        )

        service = CandidateService(engine=db_engine, vault_path=vault_path)
        candidates = service.generate_candidates()

        for c in candidates:
            assert not ({c.note_a_path, c.note_b_path} == {Path("a.md"), Path("b.md")}), (
                "Decided pair (a, b) should be excluded"
            )

    def test_stale_decision_does_not_exclude(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        """If a note has changed since the decision, the pair reappears."""
        from obsidian_note_linker.domain.note import compute_content_hash

        original_content_a = "# A\n\noriginal alpha content"
        notes = {
            "a.md": "# A\n\nmodified alpha content",
            "b.md": "# B\n\nalpha content about models",
        }
        embeddings = {
            "a.md": [0.9, 0.1],
            "b.md": [0.85, 0.15],
        }
        _setup_indexed_vault(vault_path, db_engine, notes, embeddings)

        # Decision was made on old content
        save_decision(
            engine=db_engine,
            note_a_path="a.md",
            note_b_path="b.md",
            decision="NO",
            note_a_hash=compute_content_hash(original_content_a),
            note_b_hash=compute_content_hash(notes["b.md"]),
        )

        service = CandidateService(engine=db_engine, vault_path=vault_path)
        candidates = service.generate_candidates()

        # Pair should reappear because a.md has changed
        pair_found = any(
            {c.note_a_path, c.note_b_path} == {Path("a.md"), Path("b.md")}
            for c in candidates
        )
        assert pair_found, "Pair should reappear after note modification"

    def test_candidate_has_rrf_score(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        notes = {
            "a.md": "# A\n\nalpha content",
            "b.md": "# B\n\nalpha content",
        }
        embeddings = {
            "a.md": [0.9, 0.1],
            "b.md": [0.85, 0.15],
        }
        _setup_indexed_vault(vault_path, db_engine, notes, embeddings)

        service = CandidateService(engine=db_engine, vault_path=vault_path)
        candidates = service.generate_candidates()

        assert len(candidates) >= 1
        assert candidates[0].rrf_score > 0

    def test_candidate_has_explanation(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        notes = {
            "a.md": "# A\n\nalpha content",
            "b.md": "# B\n\nalpha content",
        }
        embeddings = {
            "a.md": [0.9, 0.1],
            "b.md": [0.85, 0.15],
        }
        _setup_indexed_vault(vault_path, db_engine, notes, embeddings)

        service = CandidateService(engine=db_engine, vault_path=vault_path)
        candidates = service.generate_candidates()

        assert len(candidates) >= 1
        explanation = candidates[0].explanation
        assert "Semantic" in explanation or "semantic" in explanation.lower()
        assert len(explanation) > 10


class TestCandidateServiceCount:
    """Tests for the get_candidate_count convenience method."""

    def test_count_matches_generate_length(
        self, vault_path: Path, db_engine: Engine,
    ) -> None:
        notes = {
            "a.md": "# A\n\nalpha content here",
            "b.md": "# B\n\nalpha content here too",
            "c.md": "# C\n\nsomething different",
        }
        embeddings = {
            "a.md": [0.9, 0.1],
            "b.md": [0.85, 0.15],
            "c.md": [0.1, 0.9],
        }
        _setup_indexed_vault(vault_path, db_engine, notes, embeddings)

        service = CandidateService(engine=db_engine, vault_path=vault_path)
        candidates = service.generate_candidates()
        count = service.get_candidate_count()

        assert count == len(candidates)
