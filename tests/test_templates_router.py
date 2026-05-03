"""Tests for POST /api/templates and DELETE /api/templates/{id}."""

from __future__ import annotations

import io
import pytest


async def test_list_templates_empty(client):
    resp = await client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


async def test_upload_template_success(client, tmp_path, monkeypatch):
    import t01_llm_battle.template_service as ts
    user_dir = tmp_path / "templates"
    monkeypatch.setattr(ts, "_USER_DIR", user_dir)

    html_content = b"<html><body>Hello</body></html>"
    resp = await client.post(
        "/api/templates",
        files={"file": ("my-template.html", io.BytesIO(html_content), "text/html")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "my-template"
    assert data["source"] == "user"
    assert (user_dir / "my-template.html").read_bytes() == html_content


async def test_upload_template_non_html_rejected(client):
    resp = await client.post(
        "/api/templates",
        files={"file": ("bad.txt", io.BytesIO(b"text"), "text/plain")},
    )
    assert resp.status_code == 422


async def test_upload_template_invalid_id_rejected(client):
    resp = await client.post(
        "/api/templates",
        files={"file": ("Bad Name!.html", io.BytesIO(b"<html/>"), "text/html")},
    )
    assert resp.status_code == 422


async def test_delete_user_template_success(client, tmp_path, monkeypatch):
    import t01_llm_battle.template_service as ts
    user_dir = tmp_path / "templates"
    user_dir.mkdir()
    (user_dir / "my-tmpl.html").write_text("<html/>")
    monkeypatch.setattr(ts, "_USER_DIR", user_dir)

    resp = await client.delete("/api/templates/my-tmpl")
    assert resp.status_code == 204
    assert not (user_dir / "my-tmpl.html").exists()


async def test_delete_template_not_found(client, tmp_path, monkeypatch):
    import t01_llm_battle.template_service as ts
    monkeypatch.setattr(ts, "_USER_DIR", tmp_path / "templates")

    resp = await client.delete("/api/templates/nonexistent")
    assert resp.status_code == 404


async def test_delete_bundled_template_forbidden(client, tmp_path, monkeypatch):
    import t01_llm_battle.template_service as ts
    monkeypatch.setattr(ts, "_USER_DIR", tmp_path / "templates")

    # "card-grid" is a bundled template
    resp = await client.delete("/api/templates/card-grid")
    assert resp.status_code == 403
