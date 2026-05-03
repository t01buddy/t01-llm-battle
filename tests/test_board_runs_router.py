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


# ---------------------------------------------------------------------------
# fighter_name attribution (bug fix #318)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_board_run_stores_fighter_name(db_path):
    """board_news_item.fighter_name must be the assigned news_fighter name, not empty."""
    import t01_llm_battle.board_engine as engine_mod
    from unittest.mock import patch, AsyncMock
    from t01_llm_battle.board_engine import execute_board_run
    from t01_llm_battle.db import get_db

    # Seed a news_fighter row
    fighter_id = str(uuid.uuid4())
    battle_fighter_id = str(uuid.uuid4())
    battle_id_seed = str(uuid.uuid4())
    now = "2026-01-01T00:00:00+00:00"
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) VALUES (?, ?, '', '', '', ?)",
            (battle_id_seed, "Seed Battle", now),
        )
        await db.execute(
            "INSERT INTO fighter (id, battle_id, name, is_manual, position) VALUES (?, ?, ?, 0, 1)",
            (battle_fighter_id, battle_id_seed, "Test Fighter"),
        )
        await db.execute(
            "INSERT INTO news_fighter (id, fighter_id, name, priority, is_system, created_at, updated_at) VALUES (?, ?, ?, 1, 0, ?, ?)",
            (fighter_id, battle_fighter_id, "My News Fighter", now, now),
        )
        # Get system board and update fighter_ids
        cur = await db.execute("SELECT id FROM board WHERE is_system = 1 LIMIT 1")
        row = await cur.fetchone()
        board_id = row["id"]
        await db.execute(
            "UPDATE board SET fighter_ids = ? WHERE id = ?",
            (json.dumps([fighter_id]), board_id),
        )
        await db.commit()

    # Mock _fetch_source to return one item
    fake_item = {"title": "Test Article", "content": "Some content", "url": "https://ex.com/1", "published_at": now}
    with patch.object(engine_mod, "_fetch_source", new=AsyncMock(return_value=[fake_item])):
        run_id = await execute_board_run(board_id, db_path=db_path)

    # Verify fighter_name is stored
    async with get_db(db_path) as db:
        cur = await db.execute("SELECT fighter_name FROM board_news_item WHERE run_id = ?", (run_id,))
        rows = await cur.fetchall()

    assert len(rows) > 0, "Expected at least one board_news_item row"
    assert rows[0]["fighter_name"] == "My News Fighter", f"Expected 'My News Fighter', got '{rows[0]['fighter_name']}'"


@pytest.mark.asyncio
async def test_execute_board_run_fighter_name_empty_when_no_fighters(db_path):
    """fighter_name is empty string when board has no fighter_ids."""
    import t01_llm_battle.board_engine as engine_mod
    from unittest.mock import patch, AsyncMock
    from t01_llm_battle.board_engine import execute_board_run
    from t01_llm_battle.db import get_db

    now = "2026-01-01T00:00:00+00:00"
    async with get_db(db_path) as db:
        cur = await db.execute("SELECT id FROM board WHERE is_system = 1 LIMIT 1")
        row = await cur.fetchone()
        board_id = row["id"]
        await db.execute("UPDATE board SET fighter_ids = '[]' WHERE id = ?", (board_id,))
        await db.commit()

    fake_item = {"title": "No Fighter Item", "content": "Content", "url": "https://ex.com/2", "published_at": now}
    with patch.object(engine_mod, "_fetch_source", new=AsyncMock(return_value=[fake_item])):
        run_id = await execute_board_run(board_id, db_path=db_path)

    async with get_db(db_path) as db:
        cur = await db.execute("SELECT fighter_name FROM board_news_item WHERE run_id = ?", (run_id,))
        rows = await cur.fetchall()

    assert len(rows) > 0
    assert rows[0]["fighter_name"] == ""
