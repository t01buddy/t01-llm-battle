"""Tests for publisher.py — static export and GitHub Pages push."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from t01_llm_battle.publisher import (
    _build_data_json,
    publish_board,
    publish_static,
)


@pytest.fixture
def sample_board():
    return {"id": "b1", "name": "Tech Board", "description": "Daily tech", "template_id": None}


@pytest.fixture
def sample_items():
    return [
        {
            "title": "AI news",
            "source_url": "https://example.com/ai",
            "summary": "AI is advancing",
            "tags": ["ai", "tech"],
            "category": "tech",
            "relevance_score": 0.9,
            "published_at": None,
        }
    ]


# ---------------------------------------------------------------------------
# _build_data_json
# ---------------------------------------------------------------------------


def test_build_data_json_structure(sample_board, sample_items):
    payload = json.loads(_build_data_json(sample_board, sample_items))
    assert payload["board"]["name"] == "Tech Board"
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["title"] == "AI news"
    assert item["url"] == "https://example.com/ai"
    assert item["tags"] == ["ai", "tech"]
    assert item["score"] == 0.9


# ---------------------------------------------------------------------------
# publish_static
# ---------------------------------------------------------------------------


def test_publish_static_creates_files(tmp_path, sample_board, sample_items):
    out = str(tmp_path / "output")
    publish_static(sample_board, sample_items, out)
    assert (Path(out) / "index.html").exists()
    data = json.loads((Path(out) / "data.json").read_text())
    assert data["board"]["id"] == "b1"
    assert data["items"][0]["title"] == "AI news"


def test_publish_static_creates_output_dir(tmp_path, sample_board, sample_items):
    out = str(tmp_path / "new" / "nested" / "dir")
    publish_static(sample_board, sample_items, out)
    assert Path(out).is_dir()


# ---------------------------------------------------------------------------
# publish_board dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_board_static(tmp_path, sample_board, sample_items):
    config = {"target": "static", "output_dir": str(tmp_path / "out")}
    result = await publish_board(sample_board, sample_items, config)
    assert result["ok"] is True
    assert result["target"] == "static"
    assert (Path(result["output_dir"]) / "data.json").exists()


@pytest.mark.asyncio
async def test_publish_board_static_missing_output_dir(sample_board, sample_items):
    result = await publish_board(sample_board, sample_items, {"target": "static"})
    assert result["ok"] is False
    assert "output_dir" in result["error"]


@pytest.mark.asyncio
async def test_publish_board_github_pages_missing_token(sample_board, sample_items):
    result = await publish_board(
        sample_board, sample_items, {"target": "github_pages", "repo": "owner/repo"}
    )
    assert result["ok"] is False
    assert "gh_token" in result["error"]


@pytest.mark.asyncio
async def test_publish_board_github_pages_missing_repo(sample_board, sample_items):
    result = await publish_board(
        sample_board, sample_items, {"target": "github_pages", "gh_token": "tok"}
    )
    assert result["ok"] is False
    assert "repo" in result["error"]


@pytest.mark.asyncio
async def test_publish_board_unknown_target(sample_board, sample_items):
    result = await publish_board(sample_board, sample_items, {"target": "ftp"})
    assert result["ok"] is False
    assert "ftp" in result["error"]


@pytest.mark.asyncio
async def test_publish_board_no_target(sample_board, sample_items):
    result = await publish_board(sample_board, sample_items, {})
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_publish_board_github_pages_success(sample_board, sample_items):
    """GitHub Pages push — mock httpx to avoid real network calls."""
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {}

    with patch("t01_llm_battle.publisher.httpx.AsyncClient") as mock_client_cls:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_ctx.get = AsyncMock(return_value=MagicMock(status_code=404))
        mock_ctx.put = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_ctx

        result = await publish_board(
            sample_board,
            sample_items,
            {"target": "github_pages", "gh_token": "tok123", "repo": "owner/repo"},
        )

    assert result["ok"] is True
    assert result["repo"] == "owner/repo"
    assert result["branch"] == "gh-pages"


@pytest.mark.asyncio
async def test_publish_board_github_pages_api_error(sample_board, sample_items):
    """GitHub API error raises RuntimeError propagated out of publish_board."""
    mock_response = MagicMock()
    mock_response.status_code = 422
    mock_response.text = "Unprocessable"

    with patch("t01_llm_battle.publisher.httpx.AsyncClient") as mock_client_cls:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_ctx.get = AsyncMock(return_value=MagicMock(status_code=404))
        mock_ctx.put = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_ctx

        with pytest.raises(RuntimeError, match="GitHub API error 422"):
            await publish_board(
                sample_board,
                sample_items,
                {"target": "github_pages", "gh_token": "tok", "repo": "owner/repo"},
            )
