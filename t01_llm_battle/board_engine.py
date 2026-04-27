"""Board execution engine — fetch, dedup, load-balance, run fighters, normalize, store."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone

import httpx

from .db import DB_PATH, get_db, resolve_api_key


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _item_hash(url: str, title: str) -> str:
    return hashlib.sha256(f"{url}|{title}".encode()).hexdigest()


# --- Source fetchers ---

async def _fetch_rss(config: dict, max_items: int) -> list[dict]:
    try:
        import feedparser  # optional dep
    except ImportError:
        return []
    url = config.get("feed_url") or config.get("url", "")
    feed = feedparser.parse(url)
    items = []
    for entry in feed.entries[:max_items]:
        items.append({
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "content": entry.get("summary", entry.get("title", "")),
            "published_at": entry.get("published", None),
        })
    return items


async def _fetch_url(config: dict, max_items: int, api_key: str | None) -> list[dict]:
    url = config.get("url", "")
    if not url:
        return []
    # Use Firecrawl if key available, else plain httpx scrape
    if api_key:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.firecrawl.dev/v0/scrape",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"url": url},
                )
                data = resp.json()
                text = data.get("data", {}).get("markdown", "") or data.get("data", {}).get("content", "")
        except Exception:
            text = ""
    else:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, follow_redirects=True)
                text = resp.text[:5000]
        except Exception:
            text = ""
    if not text:
        return []
    return [{"title": url, "url": url, "content": text[:2000], "published_at": None}]


async def _fetch_api(config: dict, max_items: int, db_path) -> list[dict]:
    provider = config.get("provider", "")
    query = config.get("query", "")
    if provider == "serper":
        api_key = await resolve_api_key("serper", db_path)
        if not api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    "https://google.serper.dev/news",
                    headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                    json={"q": query, "num": max_items},
                )
                results = resp.json().get("news", [])
                return [{"title": r.get("title",""), "url": r.get("link",""), "content": r.get("snippet",""), "published_at": r.get("date")} for r in results[:max_items]]
        except Exception:
            return []
    if provider == "tavily":
        api_key = await resolve_api_key("tavily", db_path)
        if not api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={"api_key": api_key, "query": query, "max_results": max_items},
                )
                results = resp.json().get("results", [])
                return [{"title": r.get("title",""), "url": r.get("url",""), "content": r.get("content",""), "published_at": None} for r in results[:max_items]]
        except Exception:
            return []
    # HN top stories via Firebase API
    if config.get("url", "").startswith("https://hacker-news"):
        limit = min(config.get("limit", 10), max_items)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(config["url"])
                ids = resp.json()[:limit]
                items = []
                for story_id in ids[:limit]:
                    sr = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
                    story = sr.json()
                    if story and story.get("title"):
                        items.append({
                            "title": story["title"],
                            "url": story.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                            "content": story.get("text", story["title"])[:500],
                            "published_at": None,
                        })
                return items
        except Exception:
            return []
    return []


async def _fetch_social(config: dict, max_items: int) -> list[dict]:
    platform = config.get("platform", "")
    if platform == "hackernews":
        section = config.get("section", "top")
        url = f"https://hacker-news.firebaseio.com/v0/{section}stories.json"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url)
                ids = resp.json()[:max_items]
                items = []
                for story_id in ids:
                    sr = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
                    story = sr.json()
                    if story and story.get("title"):
                        items.append({
                            "title": story["title"],
                            "url": story.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                            "content": story.get("text", story["title"])[:500],
                            "published_at": None,
                        })
                return items
        except Exception:
            return []
    return []


async def _fetch_source(source: dict, db_path) -> list[dict]:
    stype = source["source_type"]
    config = json.loads(source["config"] or "{}")
    max_items = source["max_items"]
    if stype == "rss":
        return await _fetch_rss(config, max_items)
    if stype == "url":
        api_key = await resolve_api_key("firecrawl", db_path)
        return await _fetch_url(config, max_items, api_key)
    if stype == "api":
        return await _fetch_api(config, max_items, db_path)
    if stype == "social":
        return await _fetch_social(config, max_items)
    return []


# --- Normalizer ---

async def _normalize_item(raw: dict, board: dict, fighter_name: str, db_path) -> dict | None:
    """Call normalizer LLM if configured; otherwise return a basic item."""
    provider = board["normalizer_provider"]
    model = board["normalizer_model"]
    instructions = board["normalizer_instructions"] or "Summarize this content as a news item. Return JSON with: title, summary, category, tags (list), relevance_score (0-10)."

    if provider and model:
        api_key = await resolve_api_key(provider, db_path)
        if api_key:
            prompt = f"{instructions}\n\nContent:\nTitle: {raw['title']}\n{raw['content'][:1000]}"
            try:
                from .providers.registry import get_provider
                prov = get_provider(provider)
                if prov:
                    from .providers.base import ProviderRequest
                    req = ProviderRequest(model_id=model, user_prompt=prompt, api_key=api_key)
                    result = await prov.run(req)
                    text = result.output_text or ""
                    # Parse JSON from response
                    import re
                    m = re.search(r'\{.*\}', text, re.DOTALL)
                    if m:
                        data = json.loads(m.group())
                        return {
                            "title": data.get("title", raw["title"])[:500],
                            "summary": data.get("summary", "")[:2000],
                            "category": data.get("category", "")[:100],
                            "tags": data.get("tags", [])[:20],
                            "relevance_score": float(data.get("relevance_score", 5.0)),
                        }
            except Exception:
                pass

    # Fallback: basic normalization
    tags = []
    return {
        "title": raw["title"][:500],
        "summary": raw["content"][:500],
        "category": "",
        "tags": tags,
        "relevance_score": 5.0,
    }


# --- Assign items to topics ---

def _assign_topics(item_tags: list[str], topics: list[dict]) -> list[str]:
    """Return list of topic IDs that match the item's tags."""
    matched = []
    for topic in topics:
        tf = json.loads(topic["tag_filter"] or "[]")
        if not tf:
            continue
        include = [t for t in tf if not t.startswith("-")]
        exclude = [t[1:] for t in tf if t.startswith("-")]
        if exclude and any(t in item_tags for t in exclude):
            continue
        if include and any(t in item_tags for t in include):
            matched.append(topic["id"])
    return matched


# --- History pruning ---

async def _prune_history(board_id: str, max_history: int, db_path=DB_PATH) -> None:
    """Delete board_run rows (and their items) beyond max_history."""
    async with get_db(db_path) as db:
        cur = await db.execute(
            "SELECT id FROM board_run WHERE board_id = ? ORDER BY started_at DESC",
            (board_id,),
        )
        all_runs = [r["id"] for r in await cur.fetchall()]
        to_delete = all_runs[max_history:]
        for run_id in to_delete:
            await db.execute("DELETE FROM board_news_item WHERE run_id = ?", (run_id,))
            await db.execute("DELETE FROM board_run WHERE id = ?", (run_id,))
        if to_delete:
            await db.commit()


# --- Main run execution ---

async def execute_board_run(board_id: str, db_path=DB_PATH) -> str:
    """Create and execute a board run. Returns the run_id."""
    run_id = str(uuid.uuid4())
    now = _now()

    async with get_db(db_path) as db:
        # Get board
        cur = await db.execute("SELECT * FROM board WHERE id = ?", (board_id,))
        board = await cur.fetchone()
        if board is None:
            raise ValueError(f"Board {board_id} not found")
        board = dict(board)

        # Get topics
        cur = await db.execute("SELECT * FROM board_topic WHERE board_id = ? ORDER BY position", (board_id,))
        topics = [dict(r) for r in await cur.fetchall()]

        # Create run record
        await db.execute(
            "INSERT INTO board_run (id, board_id, status, started_at) VALUES (?, ?, 'running', ?)",
            (run_id, board_id, now),
        )
        await db.commit()

    try:
        # Get active sources
        source_filter = json.loads(board["source_filter"] or "[]")
        async with get_db(db_path) as db:
            if source_filter:
                # Filter by tags
                cur = await db.execute("SELECT * FROM news_source WHERE status = 'active' ORDER BY priority DESC")
                all_sources = [dict(r) for r in await cur.fetchall()]
                sources = [s for s in all_sources if any(t in json.loads(s["tags"] or "[]") for t in source_filter)]
            else:
                cur = await db.execute("SELECT * FROM news_source WHERE status = 'active' ORDER BY priority DESC")
                sources = [dict(r) for r in await cur.fetchall()]

        max_run = board["max_news_per_run"]
        all_raw: list[dict] = []

        # Fetch from each source
        fetch_tasks = [_fetch_source(src, db_path) for src in sources]
        fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        for src, items in zip(sources, fetch_results):
            if isinstance(items, Exception):
                continue
            for item in items[:src["max_items"]]:
                item["source_name"] = src["name"]
                item["source_id"] = src["id"]
                all_raw.append(item)

        items_fetched = len(all_raw)

        # Dedup
        async with get_db(db_path) as db:
            deduped = []
            seen_now = []
            for item in all_raw:
                h = _item_hash(item.get("url", ""), item.get("title", ""))
                cur = await db.execute(
                    "SELECT 1 FROM board_seen_item WHERE board_id = ? AND item_hash = ?",
                    (board_id, h),
                )
                if await cur.fetchone() is None and h not in [x[1] for x in seen_now]:
                    deduped.append(item)
                    seen_now.append((board_id, h))
            # Cap
            deduped = deduped[:max_run]

            # Record seen items
            for board_id_val, h in seen_now[:len(deduped)]:
                await db.execute(
                    "INSERT OR IGNORE INTO board_seen_item (board_id, item_hash, first_seen_at) VALUES (?, ?, ?)",
                    (board_id_val, h, now),
                )
            await db.commit()

        items_processed = len(deduped)

        # Normalize and store items
        norm_tasks = [_normalize_item(item, board, item.get("source_name", ""), db_path) for item in deduped]
        norm_results = await asyncio.gather(*norm_tasks, return_exceptions=True)

        async with get_db(db_path) as db:
            for raw, norm in zip(deduped, norm_results):
                if isinstance(norm, Exception) or norm is None:
                    continue
                item_id = str(uuid.uuid4())
                tags_json = json.dumps(norm["tags"])
                await db.execute(
                    """INSERT INTO board_news_item
                       (id, run_id, board_id, title, summary, source_url, source_name,
                        fighter_name, category, tags, relevance_score, published_at, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (item_id, run_id, board_id, norm["title"], norm["summary"],
                     raw.get("url", ""), raw.get("source_name", ""),
                     "", norm["category"], tags_json,
                     norm["relevance_score"], raw.get("published_at"), now),
                )
            # Update run as complete
            await db.execute(
                "UPDATE board_run SET status='complete', items_fetched=?, items_processed=?, finished_at=? WHERE id=?",
                (items_fetched, items_processed, _now(), run_id),
            )
            await db.commit()

        # Prune old runs beyond max_history
        await _prune_history(board_id, board["max_history"], db_path)

        # Auto-publish if configured
        publish_config = json.loads(board.get("publish_config") or "{}")
        if publish_config.get("target"):
            from .publisher import publish_board
            # Fetch stored items for this run
            async with get_db(db_path) as db:
                cur = await db.execute(
                    "SELECT * FROM board_news_item WHERE board_id = ? ORDER BY relevance_score DESC LIMIT 100",
                    (board_id,),
                )
                item_rows = [dict(r) for r in await cur.fetchall()]
            for it in item_rows:
                it["tags"] = json.loads(it.get("tags") or "[]")
            try:
                await publish_board(board, item_rows, publish_config)
            except Exception as pub_err:
                # Non-fatal: log but don't fail the run
                import logging as _log
                _log.getLogger(__name__).warning("[board_engine] auto-publish failed: %s", pub_err)

    except Exception as e:
        async with get_db(db_path) as db:
            await db.execute(
                "UPDATE board_run SET status='error', finished_at=? WHERE id=?",
                (_now(), run_id),
            )
            await db.commit()
        raise

    return run_id
