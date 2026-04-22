from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="Financial Policy RAG API")
    app_env: str = Field(default="dev")
    app_port: int = Field(default=8000)
    database_url: str = Field(default="sqlite:///./data/rag_finance.db")

    mysql_host: str = Field(default="mysql")
    mysql_port: int = Field(default=3306)
    mysql_user: str = Field(default="rag")
    mysql_password: str = Field(default="rag")
    mysql_db: str = Field(default="rag_finance")

    milvus_host: str = Field(default="milvus")
    milvus_port: int = Field(default=19530)
    milvus_collection: str = Field(default="finance_policy_chunks")
    vector_backend: Literal["disabled", "milvus"] = Field(default="disabled")

    embedding_backend: Literal["hash", "api"] = Field(default="hash")
    embedding_dimension: int = Field(default=384)
    embedding_timeout_seconds: int = Field(default=30)
    embedding_batch_size: int = Field(default=24)
    embedding_max_retries: int = Field(default=2)
    embedding_retry_backoff_ms: int = Field(default=300)
    embedding_max_connections: int = Field(default=50)
    embedding_max_keepalive_connections: int = Field(default=20)
    embedding_api_base: str = Field(default="")
    embedding_api_key: str = Field(default="")
    embedding_api_model: str = Field(default="")

    runtime_profile: Literal["dev_api", "prod_qwen"] = Field(default="prod_qwen")

    dev_api_base: str = Field(default="https://api.openai.com/v1")
    dev_api_key: str = Field(default="")
    dev_chat_model: str = Field(default="gpt-4o-mini")
    dev_embedding_model: str = Field(default="text-embedding-3-small")

    qwen_api_base: str = Field(default="http://qwen:8000/v1")
    qwen_api_key: str = Field(default="")
    qwen_chat_model: str = Field(default="Qwen2.5-14B-Instruct")
    qwen_embedding_model: str = Field(default="text-embedding-v1")
    llm_timeout_seconds: int = Field(default=35)
    rag_context_chunks: int = Field(default=4)
    rag_context_max_chars_per_chunk: int = Field(default=650)
    rag_context_max_total_chars: int = Field(default=2200)

    vector_nprobe: int = Field(default=16)
    vector_nlist: int = Field(default=128)

    ocr_lang: str = Field(default="chi_sim+eng")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def chat_profile(self) -> tuple[str, str, str]:
        if self.runtime_profile == "prod_qwen":
            return self.qwen_api_base, self.qwen_api_key, self.qwen_chat_model
        return self.dev_api_base, self.dev_api_key, self.dev_chat_model

    def embedding_profile(self) -> tuple[str, str, str]:
        if self.embedding_api_base and self.embedding_api_model:
            return self.embedding_api_base, self.embedding_api_key, self.embedding_api_model
        if self.runtime_profile == "prod_qwen":
            return self.qwen_api_base, self.qwen_api_key, self.qwen_embedding_model
        return self.dev_api_base, self.dev_api_key, self.dev_embedding_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
