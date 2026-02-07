"""Tests for the Model2Vec embedding provider.

Uses mocks to avoid downloading the actual model during tests.
"""

from unittest.mock import MagicMock, patch

from obsidian_note_linker.domain.embedding_provider import EmbeddingProvider
from obsidian_note_linker.infrastructure.model2vec_provider import Model2VecProvider


class _MockEncodeResult:
    """Mimics the numpy array returned by model2vec encode."""

    def __init__(self, data: list[list[float]]) -> None:
        self._data = data

    def tolist(self) -> list[list[float]]:
        return self._data


@patch("obsidian_note_linker.infrastructure.model2vec_provider.StaticModel")
class TestModel2VecProvider:
    """Tests for the Model2VecProvider class."""

    def test_satisfies_embedding_provider_protocol(
        self, mock_static_model_cls: MagicMock,
    ) -> None:
        mock_model = MagicMock()
        mock_model.dim = 256
        mock_static_model_cls.from_pretrained.return_value = mock_model

        provider = Model2VecProvider()

        assert isinstance(provider, EmbeddingProvider), (
            "Should satisfy EmbeddingProvider protocol"
        )

    def test_loads_model_on_init(
        self, mock_static_model_cls: MagicMock,
    ) -> None:
        mock_static_model_cls.from_pretrained.return_value = MagicMock(dim=256)

        Model2VecProvider(model_name="test/model")

        mock_static_model_cls.from_pretrained.assert_called_once_with("test/model")

    def test_uses_default_model_name(
        self, mock_static_model_cls: MagicMock,
    ) -> None:
        mock_static_model_cls.from_pretrained.return_value = MagicMock(dim=256)

        provider = Model2VecProvider()

        assert provider.model_name == "minishlab/potion-retrieval-32M"

    def test_exposes_dimension(
        self, mock_static_model_cls: MagicMock,
    ) -> None:
        mock_model = MagicMock()
        mock_model.dim = 128
        mock_static_model_cls.from_pretrained.return_value = mock_model

        provider = Model2VecProvider()

        assert provider.dimension == 128

    def test_embed_returns_list_of_lists(
        self, mock_static_model_cls: MagicMock,
    ) -> None:
        mock_model = MagicMock()
        mock_model.dim = 3
        mock_model.encode.return_value = _MockEncodeResult(
            [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
        )
        mock_static_model_cls.from_pretrained.return_value = mock_model

        provider = Model2VecProvider()
        result = provider.embed(["hello", "world"])

        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]
        assert result[1] == [0.4, 0.5, 0.6]

    def test_embed_passes_texts_to_model(
        self, mock_static_model_cls: MagicMock,
    ) -> None:
        mock_model = MagicMock()
        mock_model.dim = 2
        mock_model.encode.return_value = _MockEncodeResult([[0.1, 0.2]])
        mock_static_model_cls.from_pretrained.return_value = mock_model

        provider = Model2VecProvider()
        provider.embed(["test text"])

        mock_model.encode.assert_called_once_with(["test text"])
