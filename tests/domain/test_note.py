"""Tests for the Note domain model and content hashing."""

from pathlib import Path

import pytest

from obsidian_note_linker.domain.note import Note, compute_content_hash


class TestComputeContentHash:
    """Tests for SHA256 content hashing."""

    def test_returns_sha256_hex_digest(self) -> None:
        import hashlib

        content = "Hello, world!"
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()

        assert compute_content_hash(content) == expected, "Should return SHA256 hex digest"

    def test_empty_string_hashes_consistently(self) -> None:
        assert compute_content_hash("") == compute_content_hash(""), (
            "Empty string should hash consistently"
        )

    def test_different_content_produces_different_hashes(self) -> None:
        hash_a = compute_content_hash("content A")
        hash_b = compute_content_hash("content B")

        assert hash_a != hash_b, "Different content should produce different hashes"

    def test_hash_is_64_char_hex_string(self) -> None:
        result = compute_content_hash("anything")

        assert len(result) == 64, "SHA256 hex digest should be 64 characters"
        assert all(c in "0123456789abcdef" for c in result), "Should be lowercase hex"


class TestNote:
    """Tests for the Note frozen dataclass."""

    def test_stores_fields(self) -> None:
        note = Note(
            relative_path=Path("notes/test.md"),
            content="# Test\n\nHello world",
            content_hash="abc123",
        )

        assert note.relative_path == Path("notes/test.md"), "Should store relative_path"
        assert note.content == "# Test\n\nHello world", "Should store content"
        assert note.content_hash == "abc123", "Should store content_hash"

    def test_is_frozen(self) -> None:
        note = Note(relative_path=Path("test.md"), content="Hello", content_hash="abc")

        with pytest.raises(AttributeError):
            note.content = "modified"  # type: ignore[misc]
