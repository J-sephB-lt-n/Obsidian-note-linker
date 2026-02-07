"""CRUD operations for EmbeddingRecord persistence.

Embeddings are stored as binary blobs of single-precision (32-bit) floats
using the ``array`` module from the standard library.
"""

import array
import logging

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from obsidian_note_linker.infrastructure.models import EmbeddingRecord

logger = logging.getLogger(__name__)


def embedding_to_bytes(embedding: list[float]) -> bytes:
    """Serialise an embedding vector to a binary blob.

    Uses single-precision (32-bit) floats, 4 bytes per dimension.

    Args:
        embedding: List of float values.

    Returns:
        Binary representation of the embedding.
    """
    return array.array("f", embedding).tobytes()


def bytes_to_embedding(data: bytes) -> list[float]:
    """Deserialise a binary blob back to an embedding vector.

    Args:
        data: Binary blob produced by ``embedding_to_bytes``.

    Returns:
        List of float values.
    """
    a = array.array("f")
    a.frombytes(data)
    return a.tolist()


def get_cached_embeddings(
    engine: Engine,
    content_hashes: list[str],
) -> dict[str, list[float]]:
    """Retrieve cached embeddings for the given content hashes.

    Args:
        engine: SQLAlchemy engine.
        content_hashes: List of SHA256 content hashes to look up.

    Returns:
        Mapping of content_hash → embedding vector for hashes that
        have a cached embedding.  Missing hashes are omitted.
    """
    if not content_hashes:
        return {}

    with Session(engine) as session:
        records = session.exec(
            select(EmbeddingRecord).where(
                EmbeddingRecord.content_hash.in_(content_hashes)  # type: ignore[union-attr]
            )
        ).all()
        return {r.content_hash: bytes_to_embedding(r.embedding) for r in records}


def save_embeddings(
    engine: Engine,
    content_hashes: list[str],
    embeddings: list[list[float]],
    model_name: str,
    dimension: int,
) -> int:
    """Persist embedding vectors to the database.

    Skips content hashes that already have a cached embedding.

    Args:
        engine: SQLAlchemy engine.
        content_hashes: SHA256 content hashes (one per embedding).
        embeddings: Embedding vectors (one per content hash).
        model_name: Identifier for the embedding model used.
        dimension: Dimensionality of the embeddings.

    Returns:
        Number of new embeddings actually saved.
    """
    assert len(content_hashes) == len(embeddings), (
        f"Mismatched lengths: {len(content_hashes)} hashes, {len(embeddings)} embeddings"
    )

    saved = 0
    with Session(engine) as session:
        for content_hash, embedding in zip(content_hashes, embeddings):
            existing = session.exec(
                select(EmbeddingRecord).where(
                    EmbeddingRecord.content_hash == content_hash
                )
            ).first()
            if existing:
                continue

            record = EmbeddingRecord(
                content_hash=content_hash,
                embedding=embedding_to_bytes(embedding),
                model_name=model_name,
                dimension=dimension,
            )
            session.add(record)
            saved += 1
        session.commit()

    if saved:
        logger.info("Saved %d new embedding(s) (model=%s)", saved, model_name)
    return saved


def get_all_embeddings(engine: Engine) -> dict[str, list[float]]:
    """Retrieve all cached embeddings from the database.

    Args:
        engine: SQLAlchemy engine.

    Returns:
        Mapping of content_hash → embedding vector for every cached
        embedding.
    """
    with Session(engine) as session:
        records = session.exec(select(EmbeddingRecord)).all()
        return {r.content_hash: bytes_to_embedding(r.embedding) for r in records}


def count_embeddings(engine: Engine) -> int:
    """Return the total number of cached embeddings.

    Args:
        engine: SQLAlchemy engine.

    Returns:
        Count of embedding records in the database.
    """
    with Session(engine) as session:
        return len(list(session.exec(select(EmbeddingRecord)).all()))
