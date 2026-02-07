"""Abstract embedding provider interface."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Interface for text embedding providers.

    Implementations must provide methods to embed text into dense vectors,
    and properties exposing the model name and embedding dimensionality.

    This protocol enables swapping embedding backends (model2vec, OpenAI,
    sentence-transformers, etc.) without changing consumer code.
    """

    @property
    def model_name(self) -> str:
        """Return the identifier for the embedding model."""
        ...

    @property
    def dimension(self) -> int:
        """Return the dimensionality of the embedding vectors."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts into dense vectors.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors, one per input text.
            Each vector has length equal to ``self.dimension``.
        """
        ...
