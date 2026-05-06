"""Unit tests for LMStudioProvider (FR-6)."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from t01_llm_battle.providers.lmstudio import LMStudioProvider
from t01_llm_battle.providers.base import ProviderRequest


def test_models_returns_empty():
    """LM Studio has no model list endpoint — always returns []."""
    provider = LMStudioProvider()
    assert provider.models() == []


@pytest.mark.asyncio
async def test_run_returns_result():
    provider = LMStudioProvider(base_url="http://localhost:1234")
    request = ProviderRequest(
        model="local-model",
        system_prompt="Be helpful.",
        user_prompt="Hello!",
        api_key=None,
    )

    mock_usage = MagicMock()
    mock_usage.request_tokens = 10
    mock_usage.response_tokens = 5

    mock_result = MagicMock()
    mock_result.output = "Hi from LM Studio!"
    mock_result.usage.return_value = mock_usage

    with patch("t01_llm_battle.providers.lmstudio.resolve_base_url", new_callable=AsyncMock, return_value=None):
        with patch("t01_llm_battle.providers.lmstudio.Agent") as MockAgent:
            mock_instance = MagicMock()
            mock_instance.run = AsyncMock(return_value=mock_result)
            MockAgent.return_value = mock_instance

            result = await provider.run(request)

    assert result.content == "Hi from LM Studio!"
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.provider == "llm-studio"
    assert result.credits_used is None
    assert result.cost_usd == 0.0
    assert result.model == "local-model"


@pytest.mark.asyncio
async def test_run_uses_db_base_url():
    """run() prefers DB-configured base URL over instance default."""
    provider = LMStudioProvider(base_url="http://localhost:1234")
    request = ProviderRequest(
        model="custom-model",
        system_prompt=None,
        user_prompt="Hi",
        api_key=None,
    )

    mock_usage = MagicMock()
    mock_usage.request_tokens = 3
    mock_usage.response_tokens = 2

    mock_result = MagicMock()
    mock_result.output = "ok"
    mock_result.usage.return_value = mock_usage

    with patch("t01_llm_battle.providers.lmstudio.resolve_base_url", new_callable=AsyncMock, return_value="http://custom-lms:5678"):
        with patch("t01_llm_battle.providers.lmstudio.PAIOpenAIProvider") as MockPAI:
            mock_pai = MagicMock()
            MockPAI.return_value = mock_pai
            with patch("t01_llm_battle.providers.lmstudio.Agent") as MockAgent:
                mock_instance = MagicMock()
                mock_instance.run = AsyncMock(return_value=mock_result)
                MockAgent.return_value = mock_instance

                await provider.run(request)

            _, kwargs = MockPAI.call_args
            assert kwargs.get("base_url") == "http://custom-lms:5678/v1"


@pytest.mark.asyncio
async def test_run_uses_instance_url_when_no_db():
    """run() falls back to instance base_url when DB returns None."""
    provider = LMStudioProvider(base_url="http://localhost:1234")
    request = ProviderRequest(
        model="local-model",
        system_prompt=None,
        user_prompt="Hi",
        api_key=None,
    )

    mock_usage = MagicMock()
    mock_usage.request_tokens = 3
    mock_usage.response_tokens = 2

    mock_result = MagicMock()
    mock_result.output = "ok"
    mock_result.usage.return_value = mock_usage

    with patch("t01_llm_battle.providers.lmstudio.resolve_base_url", new_callable=AsyncMock, return_value=None):
        with patch("t01_llm_battle.providers.lmstudio.PAIOpenAIProvider") as MockPAI:
            mock_pai = MagicMock()
            MockPAI.return_value = mock_pai
            with patch("t01_llm_battle.providers.lmstudio.Agent") as MockAgent:
                mock_instance = MagicMock()
                mock_instance.run = AsyncMock(return_value=mock_result)
                MockAgent.return_value = mock_instance

                await provider.run(request)

            _, kwargs = MockPAI.call_args
            assert kwargs.get("base_url") == "http://localhost:1234/v1"
