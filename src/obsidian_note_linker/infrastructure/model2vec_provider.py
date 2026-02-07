"""Model2Vec embedding provider implementation.

Uses the ``model2vec`` library with static embeddings for fast,
local-only text embedding.  Default model is ``potion-retrieval-32M``,
optimised for English retrieval tasks.
"""

import logging

from model2vec import StaticModel

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "minishlab/potion-retrieval-32M"


class Model2VecProvider:
    """Embedding provider backed by model2vec static embeddings.

    Satisfies the ``EmbeddingProvider`` protocol defined in the domain layer.

    Args:
        model_name: HuggingFace model identifier. Defaults to
            ``minishlab/potion-retrieval-32M``.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        logger.info("Loading model2vec model: %s", model_name)
        self._model: StaticModel = StaticModel.from_pretrained(model_name)
        self._model_name = model_name
        logger.info(
            "Model loaded: %s (dimension=%d)", model_name, self.dimension,
        )

    @property
    def model_name(self) -> str:
        """Return the HuggingFace model identifier."""
        return self._model_name

    @property
    def dimension(self) -> int:
        """Return the dimensionality of the embedding vectors."""
        return self._model.dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts into dense vectors.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors, one per input text.
        """
        assert len(texts) > 0, "Cannot embed an empty list of texts"
        embeddings = self._model.encode(texts)
        return embeddings.tolist()
