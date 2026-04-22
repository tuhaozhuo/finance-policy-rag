from __future__ import annotations

import hashlib
import math
import time
from functools import lru_cache

import httpx

from app.core.config import get_settings


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = httpx.Client(
            timeout=self.settings.embedding_timeout_seconds,
            limits=httpx.Limits(
                max_connections=max(1, self.settings.embedding_max_connections),
                max_keepalive_connections=max(1, self.settings.embedding_max_keepalive_connections),
            ),
        )

    def embed_query(self, text: str) -> list[float]:
        query = text.strip()
        if not query:
            return []
        return list(self._embed_query_cached(query))

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if self.settings.embedding_backend == "api":
            embeddings = self._embed_texts_with_api(texts)
            if embeddings is not None:
                return embeddings
            raise RuntimeError("API embedding failed or returned invalid vectors")

        return [self._hash_embedding(item.strip()) for item in texts]

    def current_embedding_model(self) -> str:
        if self.settings.embedding_backend == "api":
            _, _, model = self.settings.embedding_profile()
            return model or "api-embedding"

        dim = self.settings.embedding_dimension if self.settings.embedding_dimension > 0 else 384
        return f"hash-{dim}"

    @lru_cache(maxsize=512)
    def _embed_query_cached(self, text: str) -> tuple[float, ...]:
        vectors = self.embed_texts([text])
        if not vectors:
            return tuple()
        return tuple(vectors[0])

    def _embed_texts_with_api(self, texts: list[str]) -> list[list[float]] | None:
        text_positions: dict[str, list[int]] = {}
        unique_texts: list[str] = []
        for idx, raw in enumerate(texts):
            text = raw.strip()
            if text not in text_positions:
                text_positions[text] = []
                unique_texts.append(text)
            text_positions[text].append(idx)

        if not unique_texts:
            return []

        vectors = self._embed_with_api(unique_texts)
        if vectors is None or len(vectors) != len(unique_texts):
            return None

        result: list[list[float]] = [[] for _ in texts]
        for source_idx, text in enumerate(unique_texts):
            vector = vectors[source_idx]
            for target_idx in text_positions[text]:
                result[target_idx] = vector
        return result

    def _embed_with_api(self, texts: list[str]) -> list[list[float]] | None:
        base_url, api_key, model = self.settings.embedding_profile()
        if not base_url or not model:
            return None

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        batch_size = max(1, self.settings.embedding_batch_size)
        all_vectors: list[list[float]] = []

        for start in range(0, len(texts), batch_size):
            batch = [item if item else " " for item in texts[start : start + batch_size]]
            payload = {"model": model, "input": batch}
            parsed = self._request_embedding_batch(base_url, headers, payload)
            if parsed is None or len(parsed) != len(batch):
                return None
            all_vectors.extend(parsed)
        return all_vectors

    def _request_embedding_batch(self, base_url: str, headers: dict[str, str], payload: dict[str, object]) -> list[list[float]] | None:
        retries = max(0, self.settings.embedding_max_retries)
        for attempt in range(retries + 1):
            try:
                response = self._client.post(f"{base_url.rstrip('/')}/embeddings", headers=headers, json=payload)
                response.raise_for_status()
                data = response.json().get("data", [])
                if not isinstance(data, list):
                    return None

                # 优先按 index 对齐，避免供应商返回顺序异常。
                data = sorted(data, key=lambda item: int(item.get("index", 0)))
                vectors: list[list[float]] = []
                for row in data:
                    vector = row.get("embedding")
                    if not isinstance(vector, list) or not vector:
                        return None
                    vectors.append(self._normalize_vector([float(v) for v in vector]))
                return vectors
            except Exception:
                if attempt >= retries:
                    return None
                sleep_ms = self.settings.embedding_retry_backoff_ms * (2**attempt)
                time.sleep(max(0.05, sleep_ms / 1000))
        return None

    def _normalize_vector(self, vector: list[float]) -> list[float]:
        dim = self.settings.embedding_dimension
        normalized = vector
        if dim > 0:
            if len(normalized) > dim:
                normalized = normalized[:dim]
            elif len(normalized) < dim:
                normalized = normalized + [0.0] * (dim - len(normalized))

        norm = math.sqrt(sum(v * v for v in normalized)) or 1.0
        return [v / norm for v in normalized]

    def _hash_embedding(self, text: str) -> list[float]:
        dim = self.settings.embedding_dimension if self.settings.embedding_dimension > 0 else 384
        digest = hashlib.sha256(text.encode("utf-8")).digest()

        values: list[float] = []
        for idx in range(dim):
            byte_value = digest[idx % len(digest)]
            values.append((byte_value / 127.5) - 1.0)

        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]

    def health_check(self) -> dict[str, object]:
        if self.settings.embedding_backend == "hash":
            vector = self._hash_embedding("健康检查")
            return {"status": "ok", "backend": "hash", "dimension": len(vector)}

        base_url, _, model = self.settings.embedding_profile()
        if not base_url or not model:
            return {"status": "disabled", "backend": "api", "model": model}

        vectors = self._embed_with_api(["健康检查"])
        if vectors and vectors[0]:
            return {"status": "ok", "backend": "api", "model": model, "dimension": len(vectors[0])}
        return {"status": "degraded", "backend": "api", "model": model}
