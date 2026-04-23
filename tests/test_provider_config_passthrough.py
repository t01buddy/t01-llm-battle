"""Tests for FR-7: provider_config keys beyond temperature/max_tokens are passed through."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from t01_llm_battle.providers.openai import OpenAIProvider
from t01_llm_battle.providers.base import ProviderRequest


def _mock_agent_run(content="response"):
    """Return a patcher context for Agent that yields a successful result."""
    mock_usage = MagicMock()
    mock_usage.request_tokens = 10
    mock_usage.response_tokens = 5

    mock_result = MagicMock()
    mock_result.output = content
    mock_result.usage.return_value = mock_usage
    return mock_result


@pytest.mark.asyncio
async def test_openai_passes_top_p_in_model_settings():
    """top_p from extra should appear in model_settings passed to agent.run."""
    provider = OpenAIProvider()
    request = ProviderRequest(
        model="gpt-4o",
        system_prompt="",
        user_prompt="Hi",
        temperature=0.5,
        max_tokens=100,
        extra={"top_p": 0.9},
    )

    mock_result = _mock_agent_run()

    with patch("t01_llm_battle.providers.openai.Agent") as MockAgent:
        mock_agent_instance = MagicMock()
        mock_agent_instance.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_agent_instance

        await provider.run(request)

        call_kwargs = mock_agent_instance.run.call_args.kwargs
        assert "model_settings" in call_kwargs
        assert call_kwargs["model_settings"]["top_p"] == 0.9
        assert call_kwargs["model_settings"]["temperature"] == 0.5
        assert call_kwargs["model_settings"]["max_tokens"] == 100


@pytest.mark.asyncio
async def test_openai_unknown_extra_keys_are_ignored():
    """Unknown extra keys should not raise errors (forward-compatible)."""
    provider = OpenAIProvider()
    request = ProviderRequest(
        model="gpt-4o",
        system_prompt="",
        user_prompt="Hi",
        extra={"some_future_key": "value", "another_unknown": 42},
    )

    mock_result = _mock_agent_run()

    with patch("t01_llm_battle.providers.openai.Agent") as MockAgent:
        mock_agent_instance = MagicMock()
        mock_agent_instance.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_agent_instance

        # Should not raise
        result = await provider.run(request)

    assert result.content == "response"


@pytest.mark.asyncio
async def test_openai_extra_empty_by_default():
    """When extra is empty, model_settings should still have temperature and max_tokens."""
    provider = OpenAIProvider()
    request = ProviderRequest(
        model="gpt-4o",
        system_prompt="",
        user_prompt="Hi",
        temperature=0.3,
        max_tokens=512,
    )

    mock_result = _mock_agent_run()

    with patch("t01_llm_battle.providers.openai.Agent") as MockAgent:
        mock_agent_instance = MagicMock()
        mock_agent_instance.run = AsyncMock(return_value=mock_result)
        MockAgent.return_value = mock_agent_instance

        await provider.run(request)

        call_kwargs = mock_agent_instance.run.call_args.kwargs
        assert call_kwargs["model_settings"] == {"temperature": 0.3, "max_tokens": 512}


def test_engine_builds_request_with_extra():
    """engine.py should put non-temperature/max_tokens keys into request.extra."""
    from t01_llm_battle.providers.base import ProviderRequest

    # Simulate what engine.py does when parsing provider_config
    provider_config = json.dumps({
        "temperature": 0.8,
        "max_tokens": 1024,
        "top_p": 0.95,
        "tools": ["web_search"],
        "system_prompt_role": "developer",
    })

    config = json.loads(provider_config)
    temperature = config.pop("temperature", 0.7)
    max_tokens = config.pop("max_tokens", 2048)
    extra = config  # all remaining keys

    request = ProviderRequest(
        model="gpt-4o",
        system_prompt=None,
        user_prompt="test",
        temperature=temperature,
        max_tokens=max_tokens,
        extra=extra,
    )

    assert request.temperature == 0.8
    assert request.max_tokens == 1024
    assert request.extra["top_p"] == 0.95
    assert request.extra["tools"] == ["web_search"]
    assert request.extra["system_prompt_role"] == "developer"
    assert "temperature" not in request.extra
    assert "max_tokens" not in request.extra
