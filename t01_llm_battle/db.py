"""SQLite schema initialisation and aiosqlite connection helpers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite

DB_PATH: Path = Path.home() / ".t01-llm-battle" / "battles.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS battle (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    judge_provider TEXT NOT NULL,
    judge_model   TEXT NOT NULL,
    judge_rubric  TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS battle_source (
    id         TEXT PRIMARY KEY,
    battle_id  TEXT NOT NULL REFERENCES battle(id),
    label      TEXT NOT NULL,
    content    TEXT NOT NULL,
    position   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fighter (
    id         TEXT PRIMARY KEY,
    battle_id  TEXT NOT NULL REFERENCES battle(id),
    name       TEXT NOT NULL,
    is_manual  INTEGER NOT NULL DEFAULT 0,
    position   INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS fighter_step (
    id              TEXT PRIMARY KEY,
    fighter_id      TEXT NOT NULL REFERENCES fighter(id),
    position        INTEGER NOT NULL,
    system_prompt   TEXT,
    provider        TEXT NOT NULL,
    model_id        TEXT NOT NULL,
    provider_config TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS run (
    id               TEXT PRIMARY KEY,
    battle_id        TEXT NOT NULL REFERENCES battle(id),
    status           TEXT NOT NULL DEFAULT 'pending',
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    report_markdown  TEXT
);

CREATE TABLE IF NOT EXISTS step_result (
    id             TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL REFERENCES run(id),
    fighter_id     TEXT NOT NULL REFERENCES fighter(id),
    step_id        TEXT NOT NULL REFERENCES fighter_step(id),
    source_id      TEXT NOT NULL REFERENCES battle_source(id),
    input_text     TEXT NOT NULL,
    output_text    TEXT,
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    latency_ms     INTEGER,
    cost_usd       REAL,
    error          TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fighter_result (
    id                   TEXT PRIMARY KEY,
    run_id               TEXT NOT NULL REFERENCES run(id),
    fighter_id           TEXT NOT NULL REFERENCES fighter(id),
    source_id            TEXT NOT NULL REFERENCES battle_source(id),
    final_output         TEXT,
    total_cost_usd       REAL,
    total_latency_ms     INTEGER,
    total_input_tokens   INTEGER,
    total_output_tokens  INTEGER,
    status               TEXT NOT NULL DEFAULT 'pending',
    judge_score          REAL,
    judge_reasoning      TEXT,
    created_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_key (
    provider    TEXT PRIMARY KEY,
    key_value   TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


async def init_db(db_path: str | Path = DB_PATH) -> None:
    """Create parent directory (if needed) and run all CREATE TABLE statements."""
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(path) as db:
        await db.executescript(_SCHEMA_SQL)
        await db.commit()


@asynccontextmanager
async def get_db(
    db_path: str | Path = DB_PATH,
) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async context manager that yields an aiosqlite.Connection with row_factory set."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        yield db


# Map provider slug → env var name
_PROVIDER_ENV_VARS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


async def resolve_api_key(provider: str, db_path: str | Path = DB_PATH) -> str | None:
    """Return the API key for a provider, preferring env var over DB value.

    Returns None if no key is found in either location.
    """
    import os

    env_var = _PROVIDER_ENV_VARS.get(provider)
    if env_var:
        env_val = os.environ.get(env_var)
        if env_val:
            return env_val

    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT key_value FROM api_key WHERE provider = ?", (provider,)
        )
        row = await cursor.fetchone()
        if row and row["key_value"]:
            return row["key_value"]

    return None
