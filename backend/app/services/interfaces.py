from typing import Protocol

from app.models.schemas import Citation, DocumentIngestResponse, QAResponseData, SearchRequest, SearchResult


class DocumentPipeline(Protocol):
    def ingest(self, doc_id: str, force_reindex: bool = False) -> DocumentIngestResponse: ...


class Retriever(Protocol):
    def search(self, request: SearchRequest) -> SearchResult: ...


class RAGEngine(Protocol):
    def answer(self, question: str, citations: list[Citation], include_expired: bool = False) -> QAResponseData: ...


class ConfidenceScorer(Protocol):
    def score(self, citations: list[Citation], answer: str) -> float: ...
