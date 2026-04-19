import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from t01_llm_battle.providers.openai import OpenAIProvider
from t01_llm_battle.providers.base import ProviderRequest


@pytest.mark.asyncio
async def test_run_returns_result():
    provider = OpenAIProvider()
    request = ProviderRequest(model="gpt-4o", system_prompt="", user_prompt="Hi")

    # Mock pydantic-ai Agent.run result
    mock_usage = MagicMock()
    mock_usage.request_tokens = 10
    mock_usage.response_tokens = 5

    mock_result = MagicMock()
    mock_result.data = "Hello!"
    mock_result.usage.return_value = mock_usage

    with patch("t01_llm_battle.providers.openai.Agent") as MockAgent:
        mock_agent_instance = MagicMock()
        mock_agent_instance.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_agent_instance

        result = await provider.run(request)

    assert result.content == "Hello!"
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.provider == "openai"
    assert result.credits_used is None
    assert result.cost_usd > 0  # gpt-4o has known pricing
