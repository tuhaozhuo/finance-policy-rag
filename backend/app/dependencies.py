from functools import lru_cache

from app.db.session import get_session_factory
from app.services.chunker_service import Chunker
from app.services.cleaner_service import TextCleaner
from app.services.consistency_service import AnswerConsistencyChecker
from app.services.document_pipeline_service import DocumentPipelineService
from app.services.document_service import DocumentService
from app.services.embedding_service import EmbeddingService
from app.services.ingest_task_service import IngestTaskService
from app.services.interaction_service import InteractionService
from app.services.llm_service import LLMService
from app.services.metadata_service import MetadataExtractor
from app.services.ocr_service import OCRService
from app.services.parser_service import DocumentParser
from app.services.rag_service import ConfidenceScorer, RAGService
from app.services.rerank_service import RerankService
from app.services.retriever_service import RetrieverService
from app.services.vector_store_service import VectorStoreService


@lru_cache
def get_document_service() -> DocumentService:
    return DocumentService(session_factory=get_session_factory())


@lru_cache
def get_document_pipeline() -> DocumentPipelineService:
    return DocumentPipelineService(
        session_factory=get_session_factory(),
        parser=DocumentParser(ocr_service=OCRService()),
        cleaner=TextCleaner(),
        chunker=Chunker(),
        metadata_extractor=MetadataExtractor(),
        embedding_service=get_embedding_service(),
        vector_store=get_vector_store(),
    )


@lru_cache
def get_retriever() -> RetrieverService:
    return RetrieverService(
        session_factory=get_session_factory(),
        embedding_service=get_embedding_service(),
        vector_store=get_vector_store(),
        reranker=RerankService(),
    )


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()


@lru_cache
def get_vector_store() -> VectorStoreService:
    return VectorStoreService()


@lru_cache
def get_rag_engine() -> RAGService:
    return RAGService(
        llm_service=LLMService(),
        scorer=ConfidenceScorer(),
        consistency_checker=AnswerConsistencyChecker(),
    )


@lru_cache
def get_ingest_task_service() -> IngestTaskService:
    return IngestTaskService(session_factory=get_session_factory(), pipeline=get_document_pipeline())


@lru_cache
def get_interaction_service() -> InteractionService:
    return InteractionService(session_factory=get_session_factory())
