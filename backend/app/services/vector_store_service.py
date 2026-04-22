from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings


@dataclass
class VectorRecord:
    vector_id: str
    doc_id: str
    chunk_text: str
    embedding: list[float]
    region: str | None = None
    category: str | None = None
    status: str | None = None
    article_no: str | None = None


@dataclass
class VectorHit:
    vector_id: str
    score: float


class VectorStoreService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._collection = None
        self._collection_dim: int | None = None
        self._collection_fields: set[str] = set()

    def upsert(self, records: list[VectorRecord]) -> None:
        if not records or self.settings.vector_backend != "milvus":
            return

        first_dim = len(records[0].embedding)
        if first_dim <= 0:
            return
        for item in records:
            if len(item.embedding) != first_dim:
                raise ValueError("embedding dimension mismatch in one upsert batch")

        collection = self._get_collection(expected_dim=first_dim)
        ids = [item.vector_id for item in records]
        doc_ids = [item.doc_id for item in records]
        texts = [item.chunk_text for item in records]
        vectors = [item.embedding for item in records]
        fields = self._collection_fields

        insert_data = [ids, doc_ids, texts]
        if {"region", "category", "status", "article_no"}.issubset(fields):
            insert_data.extend(
                [
                    [item.region or "" for item in records],
                    [item.category or "" for item in records],
                    [item.status or "" for item in records],
                    [item.article_no or "" for item in records],
                ]
            )
        insert_data.append(vectors)

        try:
            collection.upsert(insert_data)
        except AttributeError:
            quoted = ",".join(f'"{item}"' for item in ids)
            collection.delete(expr=f"vector_id in [{quoted}]")
            collection.insert(insert_data)

        collection.flush()

    def delete_by_doc_id(self, doc_id: str) -> None:
        if self.settings.vector_backend != "milvus" or not doc_id:
            return

        collection = self._get_collection()
        escaped = doc_id.replace("\\", "\\\\").replace('"', '\\"')
        collection.delete(expr=f'doc_id == "{escaped}"')
        collection.flush()

    def search(self, embedding: list[float], top_k: int = 20, filters: dict[str, str | None] | None = None) -> list[VectorHit]:
        if self.settings.vector_backend != "milvus":
            return []

        try:
            if not embedding:
                return []
            collection = self._get_collection(expected_dim=len(embedding))
            expr = self._build_filter_expr(filters or {})
            results = collection.search(
                data=[embedding],
                anns_field="embedding",
                param={"metric_type": "COSINE", "params": {"nprobe": max(1, self.settings.vector_nprobe)}},
                limit=max(1, min(top_k, 200)),
                expr=expr or None,
                output_fields=["doc_id"],
            )
        except Exception:
            return []

        hits: list[VectorHit] = []
        for item in results[0]:
            score = self._cosine_score(float(item.distance))
            hits.append(VectorHit(vector_id=str(item.id), score=score))
        return hits

    def _cosine_score(self, raw_score: float) -> float:
        # Milvus COSINE is similarity-oriented: larger values mean closer vectors.
        return max(0.0, min(1.0, (raw_score + 1.0) / 2.0))

    def _get_collection(self, expected_dim: int | None = None):
        if self._collection is not None:
            if expected_dim and self._collection_dim and expected_dim != self._collection_dim:
                raise ValueError(
                    f"embedding dimension mismatch, expected={expected_dim}, collection={self._collection_dim}"
                )
            return self._collection

        try:
            from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pymilvus 未安装，请在生产镜像使用 requirements.prod.txt") from exc

        connections.connect(alias="default", host=self.settings.milvus_host, port=self.settings.milvus_port)

        name = self.settings.milvus_collection
        target_dim = expected_dim or self.settings.embedding_dimension or 384
        if not utility.has_collection(name):
            schema = CollectionSchema(
                fields=[
                    FieldSchema(name="vector_id", dtype=DataType.VARCHAR, is_primary=True, max_length=80),
                    FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="chunk_text", dtype=DataType.VARCHAR, max_length=65535),
                    FieldSchema(name="region", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=128),
                    FieldSchema(name="status", dtype=DataType.VARCHAR, max_length=32),
                    FieldSchema(name="article_no", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=target_dim),
                ],
                description="finance policy chunks",
            )
            collection = Collection(name=name, schema=schema)
            index_params = {
                "index_type": "IVF_FLAT",
                "metric_type": "COSINE",
                "params": {"nlist": max(8, self.settings.vector_nlist)},
            }
            collection.create_index(field_name="embedding", index_params=index_params)
            self._collection_dim = target_dim
            self._collection_fields = self._read_collection_fields(collection)
        else:
            collection = Collection(name=name)
            self._collection_dim = self._read_collection_dim(collection)
            self._collection_fields = self._read_collection_fields(collection)
            if expected_dim and self._collection_dim and expected_dim != self._collection_dim:
                raise ValueError(
                    f"embedding dimension mismatch, expected={expected_dim}, collection={self._collection_dim}"
                )

        collection.load()
        self._collection = collection
        return collection

    def _build_filter_expr(self, filters: dict[str, str | None]) -> str:
        allowed = {"region", "category", "status", "article_no"}
        clauses: list[str] = []
        for field, raw in filters.items():
            if field not in allowed or field not in self._collection_fields or not raw or raw == "all":
                continue
            value = raw.replace("\\", "\\\\").replace('"', '\\"')
            clauses.append(f'{field} == "{value}"')
        return " and ".join(clauses)

    def _read_collection_dim(self, collection) -> int | None:
        try:
            for field in collection.schema.fields:
                if getattr(field, "name", "") != "embedding":
                    continue
                params = getattr(field, "params", None) or {}
                dim = params.get("dim")
                if dim is None:
                    return None
                return int(dim)
        except Exception:
            return None
        return None

    def _read_collection_fields(self, collection) -> set[str]:
        try:
            return {str(getattr(field, "name", "")) for field in collection.schema.fields}
        except Exception:
            return set()

    def health_check(self) -> dict[str, object]:
        if self.settings.vector_backend != "milvus":
            return {"status": "disabled", "backend": self.settings.vector_backend}
        try:
            collection = self._get_collection()
            return {
                "status": "ok",
                "backend": "milvus",
                "collection": self.settings.milvus_collection,
                "dimension": self._collection_dim,
                "fields": sorted(self._collection_fields),
                "loaded": collection is not None,
            }
        except Exception as exc:
            return {
                "status": "degraded",
                "backend": "milvus",
                "collection": self.settings.milvus_collection,
                "error": str(exc)[:200],
            }
