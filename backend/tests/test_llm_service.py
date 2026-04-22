from app.services.llm_service import LLMService


def test_context_block_is_clipped_by_config() -> None:
    service = LLMService()
    service.settings.rag_context_chunks = 2
    service.settings.rag_context_max_chars_per_chunk = 5
    service.settings.rag_context_max_total_chars = 8

    block = service._build_context_block(["第一段内容abcdef", "第二段内容uvwxyz", "第三段内容"])
    assert len(block) <= 8 + 2
    assert "第一段内" in block
