"""Unit tests for FirecrawlProvider adapter (FR-6, FR-18)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from t01_llm_battle.providers.firecrawl import FirecrawlProvider, _format_firecrawl_results
from t01_llm_battle.providers.base import ProviderRequest


def _make_request(model: str = "scrape", prompt: str = "https://example.com") -> ProviderRequest:
    return ProviderRequest(
        model=model,
        system_prompt=None,
        user_prompt=prompt,
        api_key="test-key",
    )


# ---------------------------------------------------------------------------
# _format_firecrawl_results
# ---------------------------------------------------------------------------

def test_format_scrape_with_title_and_markdown():
    data = {"data": {"metadata": {"title": "Page Title"}, "markdown": "# Hello"}}
    out = _format_firecrawl_results(data, "scrape")
    assert "Page Title" in out
    assert "# Hello" in out


def test_format_scrape_no_title():
    data = {"data": {"markdown": "Content only"}}
    out = _format_firecrawl_results(data, "scrape")
    assert "Content only" in out


def test_format_crawl_multiple_pages():
    data = {
        "data": [
            {"metadata": {"title": "Page A"}, "markdown": "A content"},
            {"metadata": {"title": "Page B"}, "markdown": "B content"},
        ]
    }
    out = _format_firecrawl_results(data, "crawl")
    assert "2 page" in out
    assert "Page A" in out
    assert "Page B" in out


def test_format_crawl_empty_pages():
    data = {"data": []}
    out = _format_firecrawl_results(data, "crawl")
    assert "0 page" in out


# ---------------------------------------------------------------------------
# FirecrawlProvider.models()
# ---------------------------------------------------------------------------

def test_models_returns_functions():
    provider = FirecrawlProvider()
    assert provider.models() == ["scrape", "crawl"]


# ---------------------------------------------------------------------------
# FirecrawlProvider.run() — pricing (FR-18)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_scrape_credits_and_cost():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"data": {"markdown": "text", "metadata": {}}}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        provider = FirecrawlProvider()
        result = await provider.run(_make_request("scrape"))

    assert result.credits_used == 1.0
    assert result.cost_usd == pytest.approx(0.001)
    assert result.provider == "firecrawl"
    assert result.model == "scrape"
    assert result.input_tokens is None
    assert result.output_tokens is None


@pytest.mark.asyncio
async def test_run_crawl_uses_crawl_endpoint():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"data": []}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        provider = FirecrawlProvider()
        result = await provider.run(_make_request("crawl"))

    call_url = mock_client.post.call_args[0][0]
    assert "crawl" in call_url
    assert result.model == "crawl"


@pytest.mark.asyncio
async def test_run_sends_bearer_auth():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"data": {"markdown": "", "metadata": {}}}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        provider = FirecrawlProvider()
        await provider.run(_make_request("scrape"))

    headers = mock_client.post.call_args[1]["headers"]
    assert headers["Authorization"] == "Bearer test-key"
