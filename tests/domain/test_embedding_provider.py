"""Tests for the EmbeddingProvider protocol."""

from obsidian_note_linker.domain.embedding_provider import EmbeddingProvider


class _FakeProvider:
    """Fake embedding provider for testing protocol conformance."""

    @property
    def model_name(self) -> str:
        return "fake-model"

    @property
    def dimension(self) -> int:
        return 3

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3]] * len(texts)


class TestEmbeddingProviderProtocol:
    """Tests for the EmbeddingProvider protocol definition."""

    def test_conforming_class_is_instance(self) -> None:
        provider = _FakeProvider()

        assert isinstance(provider, EmbeddingProvider), (
            "Conforming class should satisfy protocol"
        )

    def test_provider_returns_expected_values(self) -> None:
        provider = _FakeProvider()

        assert provider.model_name == "fake-model", "Should expose model name"
        assert provider.dimension == 3, "Should expose embedding dimension"
        assert len(provider.embed(["test"])) == 1, "Should return one embedding per input"
