"""Tests for the fighters router — CRUD for fighters and steps."""
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest

import t01_llm_battle.db as db_module
import t01_llm_battle.routers.sources as sources_module
import t01_llm_battle.routers.runs as runs_module
import t01_llm_battle.routers.fighters as fighters_module
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
    monkeypatch.setattr(fighters_module, "get_db", _get_db_override)

    app = create_app(db_path=db_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _create_battle(db_path: str) -> str:
    battle_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    async with get_db(db_path) as db:
        await db.execute(
            "INSERT INTO battle (id, name, judge_provider, judge_model, judge_rubric, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (battle_id, "Fighter Battle", "openai", "gpt-4o", "", now),
        )
        await db.commit()
    return battle_id


@pytest.mark.asyncio
async def test_create_pipeline_fighter(client, db_path):
    """Creating a pipeline fighter returns the new fighter with is_manual=False."""
    battle_id = await _create_battle(db_path)

    resp = await client.post(
        f"/battles/{battle_id}/fighters",
        json={"name": "Pipeline A", "is_manual": False, "position": 1},
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Pipeline A"
    assert data["is_manual"] is False
    assert data["battle_id"] == battle_id
    assert "id" in data


@pytest.mark.asyncio
async def test_create_manual_fighter(client, db_path):
    """Creating a manual fighter returns is_manual=True."""
    battle_id = await _create_battle(db_path)

    resp = await client.post(
        f"/battles/{battle_id}/fighters",
        json={"name": "Human Baseline", "is_manual": True, "position": 2},
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["is_manual"] is True


@pytest.mark.asyncio
async def test_add_steps_to_fighter(client, db_path):
    """Steps added to a fighter are retrievable with correct ordering."""
    battle_id = await _create_battle(db_path)

    # Create fighter
    fighter_resp = await client.post(
        f"/battles/{battle_id}/fighters",
        json={"name": "Two-step", "is_manual": False, "position": 1},
    )
    fighter_id = fighter_resp.json()["id"]

    # Add step 1
    step1_resp = await client.post(
        f"/battles/{battle_id}/fighters/{fighter_id}/steps",
        json={
            "position": 1,
            "system_prompt": "Extract key facts",
            "provider": "openai",
            "model_id": "gpt-4o-mini",
            "provider_config": '{"temperature": 0.3}',
        },
    )
    assert step1_resp.status_code == 201

    # Add step 2
    step2_resp = await client.post(
        f"/battles/{battle_id}/fighters/{fighter_id}/steps",
        json={
            "position": 2,
            "system_prompt": "Write a concise answer",
            "provider": "openai",
            "model_id": "gpt-4o",
            "provider_config": "{}",
        },
    )
    assert step2_resp.status_code == 201

    # Retrieve fighter with steps
    get_resp = await client.get(f"/battles/{battle_id}/fighters/{fighter_id}")
    assert get_resp.status_code == 200
    steps = get_resp.json()["steps"]
    assert len(steps) == 2
    assert steps[0]["position"] == 1
    assert steps[1]["position"] == 2
    assert steps[0]["system_prompt"] == "Extract key facts"


@pytest.mark.asyncio
async def test_step_ordering(client, db_path):
    """Steps are returned ordered by position ascending."""
    battle_id = await _create_battle(db_path)
    fighter_resp = await client.post(
        f"/battles/{battle_id}/fighters",
        json={"name": "Ordered", "is_manual": False, "position": 1},
    )
    fighter_id = fighter_resp.json()["id"]

    # Add in reverse order
    for pos in [3, 1, 2]:
        await client.post(
            f"/battles/{battle_id}/fighters/{fighter_id}/steps",
            json={
                "position": pos,
                "provider": "openai",
                "model_id": "gpt-4o-mini",
            },
        )

    resp = await client.get(f"/battles/{battle_id}/fighters/{fighter_id}")
    positions = [s["position"] for s in resp.json()["steps"]]
    assert positions == [1, 2, 3]


@pytest.mark.asyncio
async def test_create_fighter_battle_not_found(client, db_path):
    """Creating a fighter for a nonexistent battle returns 404."""
    resp = await client.post(
        f"/battles/{uuid.uuid4()}/fighters",
        json={"name": "Ghost", "is_manual": False, "position": 1},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_fighters(client, db_path):
    """Listing fighters returns all created fighters for a battle."""
    battle_id = await _create_battle(db_path)

    for name in ["Alpha", "Beta"]:
        await client.post(
            f"/battles/{battle_id}/fighters",
            json={"name": name, "is_manual": False, "position": 1},
        )

    resp = await client.get(f"/battles/{battle_id}/fighters")
    assert resp.status_code == 200
    names = {f["name"] for f in resp.json()}
    assert names == {"Alpha", "Beta"}


# --- DELETE /battles/{battle_id}/fighters/{fighter_id} ---

@pytest.mark.asyncio
async def test_delete_fighter_happy_path(client, db_path):
    """DELETE fighter returns 204 and fighter is no longer listed."""
    battle_id = await _create_battle(db_path)
    fighter_resp = await client.post(
        f"/battles/{battle_id}/fighters",
        json={"name": "Doomed", "is_manual": False, "position": 1},
    )
    fighter_id = fighter_resp.json()["id"]

    del_resp = await client.delete(f"/battles/{battle_id}/fighters/{fighter_id}")
    assert del_resp.status_code == 204

    list_resp = await client.get(f"/battles/{battle_id}/fighters")
    assert all(f["id"] != fighter_id for f in list_resp.json())


@pytest.mark.asyncio
async def test_delete_fighter_unknown_id_404(client, db_path):
    """DELETE fighter with unknown fighter_id returns 404."""
    battle_id = await _create_battle(db_path)
    resp = await client.delete(f"/battles/{battle_id}/fighters/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_fighter_wrong_battle_404(client, db_path):
    """DELETE fighter on wrong battle_id returns 404."""
    battle_id = await _create_battle(db_path)
    other_battle_id = await _create_battle(db_path)
    fighter_resp = await client.post(
        f"/battles/{battle_id}/fighters",
        json={"name": "Belongs Elsewhere", "is_manual": False, "position": 1},
    )
    fighter_id = fighter_resp.json()["id"]

    resp = await client.delete(f"/battles/{other_battle_id}/fighters/{fighter_id}")
    assert resp.status_code == 404


# --- PUT /battles/{battle_id}/fighters/{fighter_id}/steps/{step_id} ---

async def _create_fighter_with_step(client, battle_id):
    fighter_resp = await client.post(
        f"/battles/{battle_id}/fighters",
        json={"name": "StepOwner", "is_manual": False, "position": 1},
    )
    fighter_id = fighter_resp.json()["id"]
    step_resp = await client.post(
        f"/battles/{battle_id}/fighters/{fighter_id}/steps",
        json={"position": 1, "provider": "openai", "model_id": "gpt-4o-mini"},
    )
    step_id = step_resp.json()["id"]
    return fighter_id, step_id


@pytest.mark.asyncio
async def test_update_step_happy_path(client, db_path):
    """PUT step updates model_id and returns the updated step."""
    battle_id = await _create_battle(db_path)
    fighter_id, step_id = await _create_fighter_with_step(client, battle_id)

    resp = await client.put(
        f"/battles/{battle_id}/fighters/{fighter_id}/steps/{step_id}",
        json={"position": 1, "provider": "anthropic", "model_id": "claude-3-haiku"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_id"] == "claude-3-haiku"
    assert data["provider"] == "anthropic"


@pytest.mark.asyncio
async def test_update_step_unknown_step_404(client, db_path):
    """PUT step with unknown step_id returns 404."""
    battle_id = await _create_battle(db_path)
    fighter_resp = await client.post(
        f"/battles/{battle_id}/fighters",
        json={"name": "Lone", "is_manual": False, "position": 1},
    )
    fighter_id = fighter_resp.json()["id"]

    resp = await client.put(
        f"/battles/{battle_id}/fighters/{fighter_id}/steps/{uuid.uuid4()}",
        json={"position": 1, "provider": "openai", "model_id": "gpt-4o"},
    )
    assert resp.status_code == 404


# --- DELETE /battles/{battle_id}/fighters/{fighter_id}/steps/{step_id} ---

@pytest.mark.asyncio
async def test_delete_step_happy_path(client, db_path):
    """DELETE step returns 204 and step no longer appears on fighter."""
    battle_id = await _create_battle(db_path)
    fighter_id, step_id = await _create_fighter_with_step(client, battle_id)

    del_resp = await client.delete(
        f"/battles/{battle_id}/fighters/{fighter_id}/steps/{step_id}"
    )
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/battles/{battle_id}/fighters/{fighter_id}")
    assert all(s["id"] != step_id for s in get_resp.json()["steps"])


@pytest.mark.asyncio
async def test_delete_step_unknown_id_404(client, db_path):
    """DELETE step with unknown step_id returns 404."""
    battle_id = await _create_battle(db_path)
    fighter_resp = await client.post(
        f"/battles/{battle_id}/fighters",
        json={"name": "Lone2", "is_manual": False, "position": 1},
    )
    fighter_id = fighter_resp.json()["id"]

    resp = await client.delete(
        f"/battles/{battle_id}/fighters/{fighter_id}/steps/{uuid.uuid4()}"
    )
    assert resp.status_code == 404


# --- PATCH /battles/{battle_id}/fighters/{fighter_id}/steps/{step_id}/move ---

@pytest.mark.asyncio
async def test_move_step_down(client, db_path):
    """PATCH move step down swaps positions correctly."""
    battle_id = await _create_battle(db_path)
    fighter_resp = await client.post(
        f"/battles/{battle_id}/fighters",
        json={"name": "Mover", "is_manual": False, "position": 1},
    )
    fighter_id = fighter_resp.json()["id"]

    step_ids = []
    for pos in [1, 2]:
        s = await client.post(
            f"/battles/{battle_id}/fighters/{fighter_id}/steps",
            json={"position": pos, "provider": "openai", "model_id": "gpt-4o-mini"},
        )
        step_ids.append(s.json()["id"])

    first_step_id = step_ids[0]
    resp = await client.patch(
        f"/battles/{battle_id}/fighters/{fighter_id}/steps/{first_step_id}/move",
        params={"direction": "down"},
    )
    assert resp.status_code == 200
    positions = {s["id"]: s["position"] for s in resp.json()}
    # first step moved to position 2
    assert positions[first_step_id] == 2


@pytest.mark.asyncio
async def test_move_step_invalid_direction_400(client, db_path):
    """PATCH move step with invalid direction returns 400."""
    battle_id = await _create_battle(db_path)
    fighter_id, step_id = await _create_fighter_with_step(client, battle_id)

    resp = await client.patch(
        f"/battles/{battle_id}/fighters/{fighter_id}/steps/{step_id}/move",
        params={"direction": "sideways"},
    )
    assert resp.status_code == 400
