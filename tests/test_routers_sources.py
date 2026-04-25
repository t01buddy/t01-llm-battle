"""Tests for the sources router — upload txt and CSV source items."""
import io
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest

import t01_llm_battle.db as db_module
import t01_llm_battle.routers.sources as sources_module
import t01_llm_battle.routers.runs as runs_module
from httpx import AsyncClient, ASGITransport
from t01_llm_battle.db import get_db, init_db
from t01_llm_battle.server import create_app


@pytest.fixture
async def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    await init_db(path)
    return path


@pytest.fixture
async def client(db_path, monkeypatch):
    _db_path = db_path

    @asynccontextmanager
    async def _get_db_override(path=None):
        async with get_db(_db_path) as db:
            yield db

    monkeypatch.setattr(db_module, "DB_PATH", _db_path)
    monkeypatch.setattr(sources_module, "get_db", _get_db_override)
    monkeypatch.setattr(runs_module, "get_db", _get_db_override)

    app = create_app(db_path=db_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _create_battle(db_path: str) -> str:
    """Insert a battle and return its id."""
    battle_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Sources Battle", "openai", "gpt-4o", "", now),
        )
        await db.commit()
    return battle_id


@pytest.mark.asyncio
async def test_upload_txt_file_creates_one_source(client, db_path):
    """Uploading a .txt file creates exactly one source item."""
    battle_id = await _create_battle(db_path)

    resp = await client.post(
        f"/battles/{battle_id}/sources",
        files={"file": ("notes.txt", io.BytesIO(b"Some notes here"), "text/plain")},
    )

    assert resp.status_code == 201
    data = resp.json()
    assert "sources" in data
    assert len(data["sources"]) == 1
    assert data["sources"][0]["label"] == "notes.txt"


@pytest.mark.asyncio
async def test_upload_csv_creates_multiple_sources(client, db_path):
    """Uploading a CSV (with header) creates one source item per data row."""
    battle_id = await _create_battle(db_path)

    csv_content = b"prompt\nTell me about cats\nTell me about dogs\nTell me about fish\n"
    resp = await client.post(
        f"/battles/{battle_id}/sources",
        files={"file": ("cases.csv", io.BytesIO(csv_content), "text/csv")},
    )

    assert resp.status_code == 201
    data = resp.json()
    assert "sources" in data
    assert len(data["sources"]) == 3
    labels = [s["label"] for s in data["sources"]]
    assert labels == ["Row 1", "Row 2", "Row 3"]


@pytest.mark.asyncio
async def test_upload_to_nonexistent_battle_returns_404(client, db_path):
    """Uploading to a nonexistent battle returns 404."""
    resp = await client.post(
        f"/battles/{uuid.uuid4()}/sources",
        files={"file": ("x.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_sources_returns_items(client, db_path):
    """After uploading, listing sources returns the uploaded items."""
    battle_id = await _create_battle(db_path)

    await client.post(
        f"/battles/{battle_id}/sources",
        files={"file": ("a.txt", io.BytesIO(b"first"), "text/plain")},
    )
    await client.post(
        f"/battles/{battle_id}/sources",
        files={"file": ("b.txt", io.BytesIO(b"second"), "text/plain")},
    )

    resp = await client.get(f"/battles/{battle_id}/sources")
    assert resp.status_code == 200
    sources = resp.json()["sources"]
    assert len(sources) == 2
    labels = {s["label"] for s in sources}
    assert labels == {"a.txt", "b.txt"}


@pytest.mark.asyncio
async def test_delete_source_removes_item(client, db_path):
    """DELETE /battles/{battle_id}/sources/{source_id} removes the source."""
    battle_id = await _create_battle(db_path)

    upload_resp = await client.post(
        f"/battles/{battle_id}/sources",
        files={"file": ("del.txt", io.BytesIO(b"to delete"), "text/plain")},
    )
    assert upload_resp.status_code == 201
    source_id = upload_resp.json()["sources"][0]["id"]

    del_resp = await client.delete(f"/battles/{battle_id}/sources/{source_id}")
    assert del_resp.status_code == 204

    list_resp = await client.get(f"/battles/{battle_id}/sources")
    assert list_resp.status_code == 200
    assert list_resp.json()["sources"] == []


@pytest.mark.asyncio
async def test_delete_source_not_found_returns_404(client, db_path):
    """DELETE with a nonexistent source_id returns 404."""
    battle_id = await _create_battle(db_path)
    resp = await client.delete(f"/battles/{battle_id}/sources/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_source_wrong_battle_returns_404(client, db_path):
    """DELETE a source from a different battle returns 404 (not found for that battle)."""
    battle_a = await _create_battle(db_path)
    battle_b = await _create_battle(db_path)

    upload_resp = await client.post(
        f"/battles/{battle_a}/sources",
        files={"file": ("x.txt", io.BytesIO(b"content"), "text/plain")},
    )
    source_id = upload_resp.json()["sources"][0]["id"]

    resp = await client.delete(f"/battles/{battle_b}/sources/{source_id}")
    assert resp.status_code == 404
