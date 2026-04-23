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

CREATE TABLE IF NOT EXISTS provider_config (
    provider     TEXT PRIMARY KEY,
    enabled      INTEGER NOT NULL DEFAULT 1,
    server_url   TEXT,
    display_name TEXT,
    updated_at   TEXT NOT NULL
);
"""

# Migrations for existing DBs
_MIGRATIONS_SQL = [
    "ALTER TABLE provider_config ADD COLUMN display_name TEXT",
]


async def init_db(db_path: str | Path = DB_PATH) -> None:
    """Create parent directory (if needed) and run all CREATE TABLE statements."""
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.executescript(_SCHEMA_SQL)
        await db.commit()
        for sql in _MIGRATIONS_SQL:
            try:
                await db.execute(sql)
                await db.commit()
            except Exception:
                pass  # column already exists

    await _migrate_plaintext_keys(db_path)


async def _migrate_plaintext_keys(db_path: str | Path = DB_PATH) -> None:
    """Encrypt any plaintext API keys still in the DB (one-time migration)."""
    from .crypto import encrypt_key, is_encrypted

    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT provider, key_value FROM api_key")
        rows = await cursor.fetchall()
        for row in rows:
            if row["key_value"] and not is_encrypted(row["key_value"]):
                encrypted = encrypt_key(row["key_value"])
                await db.execute(
                    "UPDATE api_key SET key_value = ? WHERE provider = ?",
                    (encrypted, row["provider"]),
                )
        await db.commit()


@asynccontextmanager
async def get_db(
    db_path: str | Path = DB_PATH,
) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async context manager that yields an aiosqlite.Connection with row_factory set."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        db.row_factory = aiosqlite.Row
        yield db


# Map provider slug → env var name
_PROVIDER_ENV_VARS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "serper": "SERPER_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "firecrawl": "FIRECRAWL_API_KEY",
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

    from .crypto import decrypt_key, is_encrypted

    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT key_value FROM api_key WHERE provider = ?", (provider,)
        )
        row = await cursor.fetchone()
        if row and row["key_value"]:
            raw = row["key_value"]
            return decrypt_key(raw) if is_encrypted(raw) else raw

    return None


async def resolve_base_url(provider: str, db_path: str | Path = DB_PATH) -> str | None:
    """Return the configured base URL for a provider from provider_config, or None."""
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT server_url FROM provider_config WHERE provider = ?", (provider,)
        )
        row = await cursor.fetchone()
        if row and row["server_url"]:
            return row["server_url"]
    return None
