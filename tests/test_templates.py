"""Tests for board template discovery and API."""

import pytest
from pathlib import Path
from unittest.mock import patch

from t01_llm_battle.template_service import list_templates, get_template_path, get_template_html


def test_list_templates_returns_bundled():
    templates = list_templates()
    ids = [t["id"] for t in templates]
    assert "card-grid" in ids
    assert "news-feed" in ids


def test_bundled_templates_have_correct_metadata():
    templates = {t["id"]: t for t in list_templates()}
    assert templates["card-grid"]["source"] == "bundled"
    assert templates["card-grid"]["name"] == "Card Grid"
    assert templates["news-feed"]["source"] == "bundled"
    assert templates["news-feed"]["name"] == "News Feed List"


def test_get_template_path_bundled():
    path = get_template_path("card-grid")
    assert path is not None
    assert path.exists()
    assert path.suffix == ".html"


def test_get_template_path_missing():
    assert get_template_path("nonexistent-template-xyz") is None


def test_get_template_html_contains_alpine():
    html = get_template_html("card-grid")
    assert html is not None
    assert "alpinejs" in html


def test_get_template_html_news_feed_expandable():
    html = get_template_html("news-feed")
    assert html is not None
    assert "Show more" in html


def test_user_custom_templates_discovered(tmp_path):
    (tmp_path / "my-custom.html").write_text("<html>custom</html>")
    with patch("t01_llm_battle.template_service._USER_DIR", tmp_path):
        templates = list_templates()
    ids = [t["id"] for t in templates]
    assert "my-custom" in ids
    custom = next(t for t in templates if t["id"] == "my-custom")
    assert custom["source"] == "user"


def test_user_cannot_override_bundled(tmp_path):
    (tmp_path / "card-grid.html").write_text("<html>override</html>")
    with patch("t01_llm_battle.template_service._USER_DIR", tmp_path):
        templates = list_templates()
    card_grids = [t for t in templates if t["id"] == "card-grid"]
    assert len(card_grids) == 1
    assert card_grids[0]["source"] == "bundled"


def test_bundled_templates_appear_before_user(tmp_path):
    (tmp_path / "zzz-user.html").write_text("<html>user</html>")
    with patch("t01_llm_battle.template_service._USER_DIR", tmp_path):
        templates = list_templates()
    sources = [t["source"] for t in templates]
    # All bundled before user
    first_user = next((i for i, s in enumerate(sources) if s == "user"), len(sources))
    assert all(sources[i] == "bundled" for i in range(first_user))


@pytest.mark.anyio
async def test_api_list_templates():
    from httpx import AsyncClient, ASGITransport
    from t01_llm_battle.server import create_app
    app = create_app(":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(t["id"] == "card-grid" for t in data)


@pytest.mark.anyio
async def test_api_get_template_html():
    from httpx import AsyncClient, ASGITransport
    from t01_llm_battle.server import create_app
    app = create_app(":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/templates/news-feed")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.anyio
async def test_api_get_template_404():
    from httpx import AsyncClient, ASGITransport
    from t01_llm_battle.server import create_app
    app = create_app(":memory:")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/templates/does-not-exist")
    assert resp.status_code == 404
