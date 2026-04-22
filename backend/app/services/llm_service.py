from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache

import httpx

from app.core.config import get_settings

try:  # pragma: no cover - optional dependency at runtime
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    LANGCHAIN_AVAILABLE = True
except Exception:  # pragma: no cover
    LANGCHAIN_AVAILABLE = False


@dataclass
class LLMGenerationResult:
    text: str
    status: str
    degraded_reason: str | None = None


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._chain = self._build_langchain()

    def generate(self, question: str, contexts: list[str]) -> LLMGenerationResult:
        context_block = self._build_context_block(contexts)
        cache_key = hashlib.sha1(f"{question}\n{context_block}".encode("utf-8")).hexdigest()  # noqa: S324
        return self._generate_cached(question, context_block, cache_key, bool(contexts))

    @lru_cache(maxsize=512)
    def _generate_cached(self, question: str, context_block: str, _cache_key: str, has_context: bool) -> LLMGenerationResult:
        errors: list[str] = []
        if self._chain is not None:
            try:
                content = self._chain.invoke({"question": question, "context": context_block})
                if isinstance(content, str) and content.strip():
                    return LLMGenerationResult(text=content.strip(), status="success")
            except Exception as exc:
                errors.append(f"langchain: {exc}")

        # LangChain 不可用或链路失败时，回退到原始 OpenAI-Compatible 请求。
        try:
            return LLMGenerationResult(
                text=self._generate_via_httpx(question=question, context_block=context_block),
                status="success",
            )
        except Exception as exc:
            errors.append(f"httpx: {exc}")

        reason = "; ".join(errors[-2:]) or "llm unavailable"
        if has_context:
            return LLMGenerationResult(
                text=(
                    f"生成模型暂不可用，无法基于已检索条文自动生成正式答案。"
                    f"请先查看下方引用条文，并在模型服务恢复后重新提问。问题：“{question}”。"
                ),
                status="degraded",
                degraded_reason=reason[:500],
            )
        return LLMGenerationResult(
            text=f"未检索到足够条文，且生成模型暂不可用，无法对“{question}”给出高置信度结论。",
            status="degraded",
            degraded_reason=reason[:500],
        )

    def _build_context_block(self, contexts: list[str]) -> str:
        max_chunks = max(1, self.settings.rag_context_chunks)
        per_chunk = max(1, self.settings.rag_context_max_chars_per_chunk)
        total_cap = max(per_chunk, self.settings.rag_context_max_total_chars)

        picked: list[str] = []
        total = 0
        for raw in contexts[:max_chunks]:
            text = (raw or "").strip()
            if not text:
                continue
            clipped = text[:per_chunk]
            remaining = total_cap - total
            if remaining <= 0:
                break
            if len(clipped) > remaining:
                clipped = clipped[:remaining]
            picked.append(clipped)
            total += len(clipped)
        return "\n\n".join(picked)

    def _build_langchain(self):
        if not LANGCHAIN_AVAILABLE:
            return None

        base_url, api_key, model = self.settings.chat_profile()
        if not base_url or not api_key:
            return None

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是金融制度问答助手。仅根据给定条文回答，若依据不足需明确说明不确定。返回简洁答案并提示时效性风险。",
                ),
                ("human", "问题：{question}\n\n可用条文：\n{context}"),
            ]
        )
        llm = ChatOpenAI(
            model=model,
            api_key=api_key or None,
            base_url=base_url,
            temperature=0.1,
            timeout=max(5, self.settings.llm_timeout_seconds),
        )
        return prompt | llm | StrOutputParser()

    def _generate_via_httpx(self, question: str, context_block: str) -> str:
        base_url, api_key, model = self.settings.chat_profile()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        user_prompt = f"问题：{question}\n\n可用条文：\n{context_block}"
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是金融制度问答助手。仅根据给定条文回答，若依据不足需明确说明不确定。返回简洁答案并提示时效性风险。",
                },
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }

        with httpx.Client(timeout=max(5, self.settings.llm_timeout_seconds)) as client:
            response = client.post(f"{base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if isinstance(content, str) and content.strip():
            return content.strip()
        raise RuntimeError("empty LLM response")

    def health_check(self) -> dict[str, object]:
        base_url, api_key, model = self.settings.chat_profile()
        if not base_url or not model:
            return {"status": "disabled", "model": model}

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "健康检查，只回复 OK"}],
            "temperature": 0,
            "max_tokens": 4,
        }
        try:
            with httpx.Client(timeout=3) as client:
                response = client.post(f"{base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
            return {"status": "ok", "model": model}
        except Exception as exc:
            return {"status": "degraded", "model": model, "error": str(exc)[:200]}
