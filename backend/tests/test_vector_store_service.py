from __future__ import annotations

import pytest

from app.services.vector_store_service import VectorStoreService


class _Hit:
    def __init__(self, vector_id: str, distance: float) -> None:
        self.id = vector_id
        self.distance = distance


class _SearchCollection:
    def search(self, **_kwargs):
        return [[_Hit("low", -0.2), _Hit("high", 0.8)]]


class _DeleteFailureStore(VectorStoreService):
    def _get_collection(self, expected_dim=None):  # noqa: ANN001
        raise RuntimeError("milvus unavailable")


def test_cosine_score_preserves_larger_similarity_as_larger_score() -> None:
    service = VectorStoreService()
    service.settings.vector_backend = "milvus"
    service._collection_fields = set()
    service._get_collection = lambda expected_dim=None: _SearchCollection()  # type: ignore[method-assign]

    hits = service.search([0.1, 0.2], top_k=2)

    assert len(hits) == 2
    assert hits[1].score > hits[0].score
    assert hits[0].score == pytest.approx(0.4)
    assert hits[1].score == pytest.approx(0.9)


def test_delete_by_doc_id_propagates_milvus_errors() -> None:
    service = _DeleteFailureStore()
    service.settings.vector_backend = "milvus"

    with pytest.raises(RuntimeError, match="milvus unavailable"):
        service.delete_by_doc_id("doc-1")
