"""Unit tests for SerperProvider adapter (FR-6, FR-18)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from t01_llm_battle.providers.serper import SerperProvider, _format_serper_results
from t01_llm_battle.providers.base import ProviderRequest


def _make_request(model: str = "search", prompt: str = "test query") -> ProviderRequest:
    return ProviderRequest(
        model=model,
        system_prompt=None,
        user_prompt=prompt,
        api_key="test-key",
    )


# ---------------------------------------------------------------------------
# _format_serper_results
# ---------------------------------------------------------------------------

def test_format_search_results():
    data = {"organic": [{"title": "Result 1", "snippet": "Snippet 1", "link": "https://a.com"}]}
    out = _format_serper_results(data, "search")
    assert "Result 1" in out
    assert "Snippet 1" in out
    assert "https://a.com" in out


def test_format_news_results():
    data = {"news": [{"title": "News 1", "snippet": "Blurb", "link": "https://news.com"}]}
    out = _format_serper_results(data, "news")
    assert "News 1" in out
    assert "https://news.com" in out


def test_format_empty_falls_back_to_json():
    data = {"unknownKey": "value"}
    out = _format_serper_results(data, "search")
    assert "unknownKey" in out


# ---------------------------------------------------------------------------
# SerperProvider.models()
# ---------------------------------------------------------------------------

def test_models_returns_functions():
    provider = SerperProvider()
    assert provider.models() == ["search", "news"]


# ---------------------------------------------------------------------------
# SerperProvider.run() — pricing (FR-18)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_credits_and_cost():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"organic": [{"title": "T", "snippet": "S", "link": "L"}]}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        provider = SerperProvider()
        result = await provider.run(_make_request("search"))

    assert result.credits_used == 1.0
    assert result.cost_usd == pytest.approx(0.001)
    assert result.provider == "serper"
    assert result.model == "search"
    assert result.input_tokens is None
    assert result.output_tokens is None


@pytest.mark.asyncio
async def test_run_news_function_uses_news_endpoint():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"news": []}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        provider = SerperProvider()
        result = await provider.run(_make_request("news"))

    call_args = mock_client.post.call_args
    assert "news" in call_args[0][0]
    assert result.model == "news"
