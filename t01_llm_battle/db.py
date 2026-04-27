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
    judge_provider TEXT,
    judge_model   TEXT,
    judge_rubric  TEXT,
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

CREATE TABLE IF NOT EXISTS news_source (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    source_type      TEXT NOT NULL,
    config           TEXT NOT NULL DEFAULT '{}',
    tags             TEXT NOT NULL DEFAULT '[]',
    priority         INTEGER NOT NULL DEFAULT 5,
    max_items        INTEGER NOT NULL DEFAULT 20,
    fighter_affinity TEXT,
    is_system        INTEGER NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'active',
    last_error       TEXT,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS news_fighter (
    id                  TEXT PRIMARY KEY,
    fighter_id          TEXT NOT NULL REFERENCES fighter(id),
    name                TEXT NOT NULL,
    fallback_fighter_id TEXT REFERENCES news_fighter(id),
    priority            INTEGER NOT NULL DEFAULT 5,
    is_system           INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
"""

# Migrations for existing DBs
_MIGRATIONS_SQL = [
    "ALTER TABLE provider_config ADD COLUMN display_name TEXT",
    # SQLite cannot drop NOT NULL via ALTER TABLE; recreate battle table without NOT NULL on judge fields.
    "ALTER TABLE battle RENAME TO battle_old",
    """CREATE TABLE IF NOT EXISTS battle (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    judge_provider TEXT,
    judge_model   TEXT,
    judge_rubric  TEXT,
    created_at    TEXT NOT NULL
)""",
    "INSERT INTO battle SELECT id, name, judge_provider, judge_model, judge_rubric, created_at FROM battle_old",
    "DROP TABLE battle_old",
]


async def init_db(db_path: str | Path = DB_PATH) -> None:
    """Create parent directory (if needed) and run all CREATE TABLE statements."""
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        # Disable FK enforcement during schema creation and migrations to allow
        # table renames and recreations without constraint violations.
        # FK enforcement is enabled per-connection in get_db() for all runtime queries.
        await db.executescript(_SCHEMA_SQL)
        await db.commit()
        for sql in _MIGRATIONS_SQL:
            try:
                await db.execute(sql)
                await db.commit()
            except Exception:
                pass  # migration already applied

    await _seed_system_news_sources(db_path)
    await _seed_system_news_fighters(db_path)
    await _migrate_plaintext_keys(db_path)


_SYSTEM_NEWS_SOURCES = [
    {
        "id": "sys-news-hn-top",
        "name": "HN Top",
        "source_type": "api",
        "config": '{"url": "https://hacker-news.firebaseio.com/v0/topstories.json", "limit": 30}',
        "tags": '["tech", "programming", "startups"]',
        "priority": 8,
        "max_items": 30,
        "fighter_affinity": None,
    },
    {
        "id": "sys-news-techcrunch-rss",
        "name": "TechCrunch RSS",
        "source_type": "rss",
        "config": '{"url": "https://techcrunch.com/feed/"}',
        "tags": '["tech", "startups", "vc"]',
        "priority": 7,
        "max_items": 20,
        "fighter_affinity": None,
    },
    {
        "id": "sys-news-ai-news-serper",
        "name": "AI News (Serper)",
        "source_type": "api",
        "config": '{"query": "artificial intelligence news", "provider": "serper"}',
        "tags": '["ai", "ml", "research"]',
        "priority": 9,
        "max_items": 20,
        "fighter_affinity": None,
    },
    {
        "id": "sys-news-github-trending",
        "name": "GitHub Trending",
        "source_type": "url",
        "config": '{"url": "https://github.com/trending"}',
        "tags": '["code", "opensource", "tech"]',
        "priority": 6,
        "max_items": 25,
        "fighter_affinity": None,
    },
]


async def _seed_system_news_sources(db_path: str | Path = DB_PATH) -> None:
    """Insert system news sources if they don't exist yet."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    async with get_db(db_path) as db:
        for src in _SYSTEM_NEWS_SOURCES:
            cur = await db.execute("SELECT id FROM news_source WHERE id = ?", (src["id"],))
            if await cur.fetchone() is None:
                await db.execute(
                    """INSERT INTO news_source
                       (id, name, source_type, config, tags, priority, max_items,
                        fighter_affinity, is_system, status, last_error, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'active', NULL, ?, ?)""",
                    (src["id"], src["name"], src["source_type"], src["config"],
                     src["tags"], src["priority"], src["max_items"],
                     src["fighter_affinity"], now, now),
                )
        await db.commit()


# System news fighters: each needs a dummy battle + fighter + step, then a news_fighter row.
_SYSTEM_NEWS_FIGHTERS = [
    {
        "id": "sys-nf-general-summarizer",
        "fighter_id": "sys-nf-fighter-general-summarizer",
        "name": "General Summarizer",
        "priority": 8,
        "system_prompt": "Summarize the following news article in 3 bullet points.",
        "provider": "openai",
        "model_id": "gpt-4o-mini",
    },
    {
        "id": "sys-nf-tech-deep-dive",
        "fighter_id": "sys-nf-fighter-tech-deep-dive",
        "name": "Tech Deep Dive",
        "priority": 7,
        "system_prompt": "Analyze the technical aspects of this article. What are the key innovations and implications?",
        "provider": "openai",
        "model_id": "gpt-4o",
    },
    {
        "id": "sys-nf-youtube-analyzer",
        "fighter_id": "sys-nf-fighter-youtube-analyzer",
        "name": "YouTube Analyzer",
        "priority": 6,
        "system_prompt": "Summarize this YouTube video content, focusing on key takeaways and actionable insights.",
        "provider": "openai",
        "model_id": "gpt-4o-mini",
    },
]

_SYS_BATTLE_ID = "sys-news-fighters-battle"


async def _seed_system_news_fighters(db_path: str | Path = DB_PATH) -> None:
    """Insert system news fighters (and their battle/fighter/step rows) if not present."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    async with get_db(db_path) as db:
        # Ensure system battle exists (no FK enforcement during seeding)
        cur = await db.execute("SELECT id FROM battle WHERE id = ?", (_SYS_BATTLE_ID,))
        if await cur.fetchone() is None:
            await db.execute(
                "INSERT INTO battle (id, name, created_at) VALUES (?, ?, ?)",
                (_SYS_BATTLE_ID, "System News Fighters", now),
            )

        for nf in _SYSTEM_NEWS_FIGHTERS:
            # Skip if news_fighter already seeded
            cur = await db.execute("SELECT id FROM news_fighter WHERE id = ?", (nf["id"],))
            if await cur.fetchone() is not None:
                continue

            # Create fighter row
            cur = await db.execute("SELECT id FROM fighter WHERE id = ?", (nf["fighter_id"],))
            if await cur.fetchone() is None:
                await db.execute(
                    "INSERT INTO fighter (id, battle_id, name, is_manual, position, created_at) VALUES (?, ?, ?, 0, 0, ?)",
                    (nf["fighter_id"], _SYS_BATTLE_ID, nf["name"], now),
                )
                step_id = "sys-nf-step-" + nf["id"]
                await db.execute(
                    """INSERT INTO fighter_step (id, fighter_id, position, system_prompt, provider, model_id, provider_config, created_at)
                       VALUES (?, ?, 0, ?, ?, ?, '{}', ?)""",
                    (step_id, nf["fighter_id"], nf["system_prompt"], nf["provider"], nf["model_id"], now),
                )

            await db.execute(
                """INSERT INTO news_fighter (id, fighter_id, name, fallback_fighter_id, priority, is_system, created_at, updated_at)
                   VALUES (?, ?, ?, NULL, ?, 1, ?, ?)""",
                (nf["id"], nf["fighter_id"], nf["name"], nf["priority"], now, now),
            )

        await db.commit()


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
        await db.execute("PRAGMA foreign_keys = ON")
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
