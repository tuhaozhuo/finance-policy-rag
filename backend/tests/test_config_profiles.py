from app.core.config import Settings


def test_embedding_profile_follows_runtime_profile_when_no_override() -> None:
    settings = Settings(
        runtime_profile="prod_qwen",
        qwen_api_base="http://qwen:8000/v1",
        qwen_api_key="<test-qwen-key>",
        qwen_embedding_model="qwen-embed",
    )
    assert settings.embedding_profile() == ("http://qwen:8000/v1", "<test-qwen-key>", "qwen-embed")


def test_embedding_profile_can_use_dedicated_provider_override() -> None:
    settings = Settings(
        runtime_profile="prod_qwen",
        qwen_api_base="http://qwen:8000/v1",
        qwen_api_key="<test-qwen-key>",
        qwen_embedding_model="qwen-embed",
        embedding_api_base="https://api.siliconflow.cn/v1",
        embedding_api_key="<test-embed-key>",
        embedding_api_model="embed-model",
    )
    assert settings.embedding_profile() == ("https://api.siliconflow.cn/v1", "<test-embed-key>", "embed-model")
