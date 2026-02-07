"""Tests for embedding store CRUD and binary serialisation."""

import pytest
from sqlalchemy.engine import Engine

from obsidian_note_linker.infrastructure.embedding_store import (
    bytes_to_embedding,
    count_embeddings,
    embedding_to_bytes,
    get_cached_embeddings,
    save_embeddings,
)


class TestEmbeddingSerialization:
    """Tests for embedding ↔ bytes conversion."""

    def test_round_trip_preserves_values(self) -> None:
        original = [0.1, 0.2, 0.3, -1.0, 0.0]
        blob = embedding_to_bytes(original)
        restored = bytes_to_embedding(blob)

        assert restored == pytest.approx(original), "Round-trip should preserve values"

    def test_bytes_length_matches_dimension(self) -> None:
        embedding = [1.0, 2.0, 3.0]
        blob = embedding_to_bytes(embedding)

        assert len(blob) == 12, "3 floats × 4 bytes = 12 bytes"

    def test_empty_embedding(self) -> None:
        blob = embedding_to_bytes([])
        restored = bytes_to_embedding(blob)

        assert restored == []


class TestSaveEmbeddings:
    """Tests for persisting embeddings."""

    def test_saves_new_embeddings(self, db_engine: Engine) -> None:
        saved = save_embeddings(
            db_engine,
            content_hashes=["hash1", "hash2"],
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
            model_name="test-model",
            dimension=2,
        )

        assert saved == 2
        assert count_embeddings(db_engine) == 2

    def test_skips_already_cached(self, db_engine: Engine) -> None:
        save_embeddings(
            db_engine,
            content_hashes=["hash1"],
            embeddings=[[0.1, 0.2]],
            model_name="test-model",
            dimension=2,
        )

        saved = save_embeddings(
            db_engine,
            content_hashes=["hash1", "hash2"],
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
            model_name="test-model",
            dimension=2,
        )

        assert saved == 1, "Should only save the new one"
        assert count_embeddings(db_engine) == 2

    def test_raises_on_mismatched_lengths(self, db_engine: Engine) -> None:
        with pytest.raises(AssertionError, match="Mismatched lengths"):
            save_embeddings(
                db_engine,
                content_hashes=["h1", "h2"],
                embeddings=[[0.1]],
                model_name="m",
                dimension=1,
            )


class TestGetCachedEmbeddings:
    """Tests for retrieving cached embeddings."""

    def test_returns_empty_for_no_matches(self, db_engine: Engine) -> None:
        result = get_cached_embeddings(db_engine, content_hashes=["missing"])

        assert result == {}

    def test_returns_matching_embeddings(self, db_engine: Engine) -> None:
        save_embeddings(
            db_engine,
            content_hashes=["h1", "h2"],
            embeddings=[[1.0, 2.0], [3.0, 4.0]],
            model_name="test",
            dimension=2,
        )

        result = get_cached_embeddings(db_engine, content_hashes=["h1"])

        assert "h1" in result
        assert result["h1"] == pytest.approx([1.0, 2.0])

    def test_omits_missing_hashes(self, db_engine: Engine) -> None:
        save_embeddings(
            db_engine,
            content_hashes=["h1"],
            embeddings=[[1.0]],
            model_name="test",
            dimension=1,
        )

        result = get_cached_embeddings(db_engine, content_hashes=["h1", "missing"])

        assert "h1" in result
        assert "missing" not in result

    def test_empty_hash_list_returns_empty(self, db_engine: Engine) -> None:
        assert get_cached_embeddings(db_engine, content_hashes=[]) == {}


class TestCountEmbeddings:
    """Tests for counting cached embeddings."""

    def test_zero_when_empty(self, db_engine: Engine) -> None:
        assert count_embeddings(db_engine) == 0

    def test_counts_all(self, db_engine: Engine) -> None:
        save_embeddings(
            db_engine,
            content_hashes=["h1", "h2"],
            embeddings=[[1.0], [2.0]],
            model_name="m",
            dimension=1,
        )

        assert count_embeddings(db_engine) == 2
