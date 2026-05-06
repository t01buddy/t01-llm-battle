"""Unit tests for TavilyProvider adapter (FR-6, FR-18)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from t01_llm_battle.providers.tavily import TavilyProvider, _format_tavily_results
from t01_llm_battle.providers.base import ProviderRequest


def _make_request(prompt: str = "test query") -> ProviderRequest:
    return ProviderRequest(
        model="search",
        system_prompt=None,
        user_prompt=prompt,
        api_key="test-key",
    )


# ---------------------------------------------------------------------------
# _format_tavily_results
# ---------------------------------------------------------------------------

def test_format_with_answer_and_results():
    data = {
        "answer": "42",
        "results": [{"title": "Source", "content": "Details", "url": "https://src.com"}],
    }
    out = _format_tavily_results(data)
    assert "42" in out
    assert "Source" in out
    assert "https://src.com" in out


def test_format_no_answer():
    data = {"results": [{"title": "T", "content": "C", "url": "https://u.com"}]}
    out = _format_tavily_results(data)
    assert "Answer" not in out
    assert "T" in out


def test_format_empty_results():
    out = _format_tavily_results({})
    assert out == ""


# ---------------------------------------------------------------------------
# TavilyProvider.models()
# ---------------------------------------------------------------------------

def test_models_returns_functions():
    provider = TavilyProvider()
    assert provider.models() == ["search"]


# ---------------------------------------------------------------------------
# TavilyProvider.run() — pricing (FR-18)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_credits_and_cost():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"answer": "yes", "results": []}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        provider = TavilyProvider()
        result = await provider.run(_make_request())

    assert result.credits_used == 1.0
    assert result.cost_usd == pytest.approx(0.002)
    assert result.provider == "tavily"
    assert result.model == "search"
    assert result.input_tokens is None
    assert result.output_tokens is None


@pytest.mark.asyncio
async def test_run_sends_api_key_in_body():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"results": []}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        provider = TavilyProvider()
        await provider.run(_make_request())

    call_json = mock_client.post.call_args[1]["json"]
    assert call_json["api_key"] == "test-key"
