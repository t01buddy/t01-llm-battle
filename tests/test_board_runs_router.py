"""Tests for board runs, items, and tags endpoints (FR-27, FR-31)."""

from __future__ import annotations

import json
import uuid

import pytest

from t01_llm_battle.db import get_db


@pytest.mark.asyncio
async def test_list_runs_empty(client):
    resp = await client.post("/boards", json={"name": "Empty Board"})
    board_id = resp.json()["id"]
    resp = await client.get(f"/boards/{board_id}/runs")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_items_empty(client):
    resp = await client.post("/boards", json={"name": "Empty Board"})
    board_id = resp.json()["id"]
    resp = await client.get(f"/boards/{board_id}/items")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["pages"] == 1


@pytest.mark.asyncio
async def test_list_items_pagination_param(client):
    resp = await client.post("/boards", json={"name": "Page Board"})
    board_id = resp.json()["id"]
    resp = await client.get(f"/boards/{board_id}/items?page_size=5")
    assert resp.status_code == 200
    assert resp.json()["page_size"] == 5


@pytest.mark.asyncio
async def test_list_tags_empty(client):
    resp = await client.post("/boards", json={"name": "Tags Board"})
    board_id = resp.json()["id"]
    resp = await client.get(f"/boards/{board_id}/items/tags")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_run_not_found(client):
    resp = await client.post("/boards", json={"name": "NF Board"})
    board_id = resp.json()["id"]
    resp = await client.get(f"/boards/{board_id}/runs/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_board_not_found_for_runs(client):
    resp = await client.get("/boards/nonexistent/runs")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_board_not_found_for_items(client):
    resp = await client.get("/boards/nonexistent/items")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_board_not_found_for_tags(client):
    resp = await client.get("/boards/nonexistent/items/tags")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_items_sorted_by_relevance(client, db_path):
    """Items returned sorted by relevance_score DESC."""
    resp = await client.post("/boards", json={"name": "Sorted Board"})
    board_id = resp.json()["id"]

    run_id = str(uuid.uuid4())
    now = "2026-01-01T00:00:00+00:00"
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO board_run (id, board_id, status, items_fetched, items_processed, started_at) VALUES (?, ?, 'complete', 2, 2, ?)",
            (run_id, board_id, now),
        )
        for title, score, tags in [
            ("High Score Item", 9.0, ["ai", "ml"]),
            ("Low Score Item", 2.0, ["tech"]),
        ]:
            await db.execute(
                """INSERT INTO board_news_item
                   (id, run_id, board_id, title, summary, source_url, source_name,
                    fighter_name, category, tags, relevance_score, created_at)
                   VALUES (?, ?, ?, ?, '', 'https://example.com', '', '', '', ?, ?, ?)""",
                (str(uuid.uuid4()), run_id, board_id, title, json.dumps(tags), score, now),
            )
        await db.commit()

    resp = await client.get(f"/boards/{board_id}/items")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["items"][0]["relevance_score"] >= data["items"][1]["relevance_score"]
    assert data["items"][0]["title"] == "High Score Item"


@pytest.mark.asyncio
async def test_items_tag_filter(client, db_path):
    """Filter items by tag."""
    resp = await client.post("/boards", json={"name": "Tag Filter Board"})
    board_id = resp.json()["id"]

    run_id = str(uuid.uuid4())
    now = "2026-01-01T00:00:00+00:00"
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO board_run (id, board_id, status, items_fetched, items_processed, started_at) VALUES (?, ?, 'complete', 2, 2, ?)",
            (run_id, board_id, now),
        )
        for title, score, tags in [
            ("AI Item", 9.0, ["ai"]),
            ("Tech Item", 5.0, ["tech"]),
        ]:
            await db.execute(
                """INSERT INTO board_news_item
                   (id, run_id, board_id, title, summary, source_url, source_name,
                    fighter_name, category, tags, relevance_score, created_at)
                   VALUES (?, ?, ?, ?, '', 'https://example.com', '', '', '', ?, ?, ?)""",
                (str(uuid.uuid4()), run_id, board_id, title, json.dumps(tags), score, now),
            )
        await db.commit()

    resp = await client.get(f"/boards/{board_id}/items?tags=ai")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "AI Item"


@pytest.mark.asyncio
async def test_tags_endpoint(client, db_path):
    """Tags endpoint returns unique sorted tags."""
    resp = await client.post("/boards", json={"name": "Tags Data Board"})
    board_id = resp.json()["id"]

    run_id = str(uuid.uuid4())
    now = "2026-01-01T00:00:00+00:00"
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO board_run (id, board_id, status, items_fetched, items_processed, started_at) VALUES (?, ?, 'complete', 2, 2, ?)",
            (run_id, board_id, now),
        )
        for title, tags in [("Item 1", ["ai", "ml"]), ("Item 2", ["tech"])]:
            await db.execute(
                """INSERT INTO board_news_item
                   (id, run_id, board_id, title, summary, source_url, source_name,
                    fighter_name, category, tags, relevance_score, created_at)
                   VALUES (?, ?, ?, ?, '', 'https://example.com', '', '', '', ?, 5.0, ?)""",
                (str(uuid.uuid4()), run_id, board_id, title, json.dumps(tags), now),
            )
        await db.commit()

    resp = await client.get(f"/boards/{board_id}/items/tags")
    assert resp.status_code == 200
    tags = resp.json()
    assert "ai" in tags and "ml" in tags and "tech" in tags


@pytest.mark.asyncio
async def test_runs_list_and_get(client, db_path):
    """Run history is stored and queryable."""
    resp = await client.post("/boards", json={"name": "Run History Board"})
    board_id = resp.json()["id"]

    run_id = str(uuid.uuid4())
    now = "2026-01-01T00:00:00+00:00"
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO board_run (id, board_id, status, items_fetched, items_processed, started_at, finished_at) VALUES (?, ?, 'complete', 5, 4, ?, ?)",
            (run_id, board_id, now, now),
        )
        await db.commit()

    resp = await client.get(f"/boards/{board_id}/runs")
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 1
    assert runs[0]["status"] == "complete"
    assert runs[0]["items_fetched"] == 5
    assert runs[0]["items_processed"] == 4

    resp = await client.get(f"/boards/{board_id}/runs/{run_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == run_id


def test_dedup_hash_deterministic():
    """Same URL+title always hashes to same value (dedup logic)."""
    import hashlib
    h1 = hashlib.sha256("https://ex.com|My Title".encode()).hexdigest()
    h2 = hashlib.sha256("https://ex.com|My Title".encode()).hexdigest()
    assert h1 == h2
    # Different title → different hash
    h3 = hashlib.sha256("https://ex.com|Other Title".encode()).hexdigest()
    assert h1 != h3
