import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from t01_llm_battle.providers.openai import OpenAIProvider
from t01_llm_battle.providers.base import CompletionRequest


@pytest.mark.asyncio
async def test_complete_returns_result():
    mock_response = {
        "choices": [{"message": {"content": "Hello!"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        "model": "gpt-4o",
    }
    provider = OpenAIProvider()
    request = CompletionRequest(model="gpt-4o", system_prompt="", user_prompt="Hi")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_response

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await provider.complete(request)

    assert result.content == "Hello!"
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.provider == "openai"
