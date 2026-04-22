from __future__ import annotations

import pytest

from app.services.embedding_service import EmbeddingService


class _FakeResponse:
    def __init__(self, data: list[dict]) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"data": self._data}


class _FakeEmbeddingClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def post(self, url: str, headers: dict, json: dict):  # noqa: A002
        self.calls.append({"url": url, "headers": headers, "json": json})
        payload_inputs = json["input"]
        rows = []
        for idx, _ in enumerate(payload_inputs):
            rows.append({"index": idx, "embedding": [1.0 + idx, 2.0, 3.0, 4.0, 5.0]})
        return _FakeResponse(rows)


class _FailClient:
    def post(self, *_args, **_kwargs):
        raise RuntimeError("network down")


def test_embedding_api_deduplicate_and_normalize_dimension() -> None:
    service = EmbeddingService()
    service.settings.embedding_backend = "api"
    service.settings.embedding_dimension = 4
    service.settings.embedding_batch_size = 8
    service.settings.embedding_max_retries = 0
    service.settings.embedding_api_base = "https://example.com/v1"
    service.settings.embedding_api_model = "test-embed"
    service._client = _FakeEmbeddingClient()

    vectors = service.embed_texts(["同一问题", "同一问题", "另一个问题"])
    assert len(vectors) == 3
    assert vectors[0] == vectors[1]
    assert len(vectors[0]) == 4
    assert len(service._client.calls) == 1


def test_embedding_api_failure_raises_instead_of_hash_fallback() -> None:
    service = EmbeddingService()
    service.settings.embedding_backend = "api"
    service.settings.embedding_dimension = 16
    service.settings.embedding_max_retries = 0
    service.settings.embedding_api_base = "https://example.com/v1"
    service.settings.embedding_api_model = "test-embed"
    service._client = _FailClient()

    with pytest.raises(RuntimeError, match="API embedding failed"):
        service.embed_texts(["回退测试"])
