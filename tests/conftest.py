from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import t01_llm_battle.db as db_module
import t01_llm_battle.routers.runs as runs_module
import t01_llm_battle.routers.sources as sources_module
import t01_llm_battle.routers.boards as boards_module
from httpx import AsyncClient, ASGITransport
from t01_llm_battle.db import init_db, get_db
from t01_llm_battle.server import create_app


@pytest.fixture
async def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    await init_db(path)
    return path


@pytest.fixture
async def client(db_path, monkeypatch):
    """HTTP test client wired to an isolated SQLite database.

    Replaces the get_db context manager in all router modules with a
    version that always connects to the test database.
    """
    _db_path = db_path

    @asynccontextmanager
    async def _get_db_override(path=None):
        async with get_db(_db_path) as db:
            yield db

    monkeypatch.setattr(db_module, "DB_PATH", Path(_db_path))
    monkeypatch.setattr(runs_module, "get_db", _get_db_override)
    monkeypatch.setattr(sources_module, "get_db", _get_db_override)
    monkeypatch.setattr(boards_module, "get_db", _get_db_override)

    app = create_app(db_path=db_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
