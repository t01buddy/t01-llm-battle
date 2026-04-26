# News & Trending Boards

**Version**: 0.2 (planned)
**Status**: Draft

## Overview

Boards extend t01-llm-battle from one-shot battle comparisons to **ongoing, scheduled news monitoring**. A board maintains a pool of data sources (URLs, RSS feeds, APIs, social feeds), runs prebuilt fighter pipelines to analyze and summarize content, then uses a **normalizer** (like the judge in battles) to convert raw output into a standard news item schema with tags, categories, and relevance scores. Items are organized into user-defined **topics** with dynamic filtering and pagination.

| Concept | Battle (v0.1) | Board (v0.2) |
|---------|---------------|--------------|
| Purpose | One-time comparison | Ongoing monitoring |
| Sources | Static files/CSV upload | Live feeds (URL, RSS, API, social) |
| Execution | Manual trigger | Scheduled (cron) |
| Fighters | Multiple competing | Prebuilt analysis pipeline(s) |
| Result processing | Judge (score + reasoning) | Normalizer (standardize + classify + rank) |
| Output | Markdown report | Structured JSON → topics → templates |
| Publishing | None (local only) | Local templates + GitHub Pages + static export |

---

## Source Pool

A global pool of data sources, managed independently from boards and fighters.

### Source Types

| Type | Example | Fetch Method | Config |
|------|---------|-------------|--------|
| URL | `https://news.ycombinator.com` | Firecrawl scrape | `{"url": "...", "selector": "..."}` |
| RSS | `https://blog.example.com/feed.xml` | feedparser | `{"feed_url": "..."}` |
| API | Serper news, Tavily search | Existing tool providers | `{"provider": "serper", "function": "news", "query": "..."}` |
| Social | HackerNews top, Reddit subreddit | httpx + public API | `{"platform": "hackernews", "section": "top"}` |

### Source Properties

- **Tags**: user-defined labels for categorization (e.g., `["ai", "youtube", "crypto"]`)
- **Priority**: configurable, 1 = highest. High-priority sources are fetched first during a run.
- **Max items per source**: configurable, default 5. Limits items collected per source per run.
- **Fighter affinity** (optional): list of news fighter IDs suitable for this source. If empty, any fighter can process it. Example: YouTube URL sources are reserved for a "YouTube Analyzer" fighter.
- **Status**: `active` / `paused` / `error` (auto-set on fetch failure)
- **System sources**: prebuilt, shipped with product, user can disable but not delete

### System Sources (ship with product)

| Name | Type | Config |
|------|------|--------|
| HackerNews Top Stories | social | `{"platform": "hackernews", "section": "top"}` |
| TechCrunch | rss | `{"feed_url": "https://techcrunch.com/feed/"}` |
| AI/ML News | api | `{"provider": "serper", "function": "news", "query": "artificial intelligence machine learning"}` |
| GitHub Trending | url | `{"url": "https://github.com/trending"}` |

### Source Management UI

Dedicated section in the app:
- CRUD: add, edit, delete sources
- Config: type picker → type-specific form, tags, priority, max items, fighter affinity
- Bulk operations: enable/disable by tag
- Health: show last fetch status, error count, last successful fetch time

---

## News Fighters

A news fighter is an existing fighter (from any battle) that has been **promoted** to the news fighters list, or a system-provided prebuilt fighter.

### Promotion from Battle

- "Add to News Fighters" button on battle fighter cards
- Copies the fighter + all its steps to the news fighters list
- The copy is independent — editing the original battle fighter does not affect the news fighter

### System Fighters (ship with product)

| Name | Description | Steps |
|------|-------------|-------|
| General News Summarizer | Summarize + categorize + score relevance | 1 step: LLM summarization |
| Tech Deep Dive | Detailed analysis with key takeaways | 2 steps: extract facts → analyze |
| YouTube Analyzer | Extract video metadata, summarize transcript | 1 step: specialized for video content |

### Fallback Chain

Each news fighter has an optional `fallback_fighter_id`. If a fighter fails (error, timeout) when processing a source item, the item is retried with the fallback fighter. Maximum 1 retry.

### Priority

Fighters have a configurable priority (1 = highest). Higher-priority fighters pick sources first during load balancing.

---

## Normalizer

Like the **judge** in battles, the normalizer is a dedicated LLM step that runs after fighters produce raw output. It converts raw results into the **standard news item schema**.

### Responsibilities

1. Parse raw fighter output (may be markdown, free text, or partial JSON)
2. Extract individual news items
3. For each item: generate `title`, `summary`, `source_url`, `category`, `tags` (array), `relevance_score` (0–10), `published_at`
4. Rank items by relevance
5. Output valid JSON array conforming to the standard schema

### Standard News Item Schema

```json
{
  "title": "OpenAI releases GPT-5",
  "summary": "OpenAI announced GPT-5 with improved reasoning capabilities...",
  "source_url": "https://techcrunch.com/2026/04/25/openai-gpt-5",
  "source_name": "TechCrunch",
  "fighter_name": "General News Summarizer",
  "category": "Product Launch",
  "tags": ["ai", "openai", "gpt", "llm"],
  "relevance_score": 9.2,
  "published_at": "2026-04-25T10:00:00Z"
}
```

### Normalizer Config (per board)

- **Provider + model**: like judge config in battles (e.g., `google` / `gemini-2.0-flash`)
- **Instructions**: editable system prompt (like judge rubric). Controls categorization, tagging strategy, and ranking criteria.
- **Default**: use a fast, cheap model to minimize cost per run

---

## Topics

User-defined categories for organizing news within a board.

### Definition

Each topic has:
- **Name**: e.g., "AI Research", "Product Launches", "Open Source"
- **Description**: optional context
- **Tag filter**: JSON rule matching item tags. Example: `{"include": ["ai", "research"], "exclude": ["spam"]}`

### Item → Topic Assignment

After normalization, each news item's `tags` array is matched against topic filter rules. One item can appear in multiple topics.

### "All" Topic

Built-in, always present. Shows all news items ranked by `relevance_score` descending, no filter applied.

### Topic Detail Page

- Shows items matching the topic's tag filter
- **Dynamic filters**: header chips showing all unique tags within the current topic. User clicks tags to further narrow results.
- **Pagination**: configurable page size (default 20), sorted by `relevance_score` descending
- **Each item shows**: title, summary, source name, relevance score, tags (as chips), published date, link to original source

---

## Load Balancing & Execution

When a board run triggers (scheduled or manual):

1. **Fetch sources**: ordered by priority (highest first). Each source returns max N items (per-source `max_items`, default 5).
2. **Dedup**: hash items by URL + title (`SHA-256`), skip items already in `board_seen_item`.
3. **Cap**: total items capped at board's `max_news_per_run` (default 100).
4. **Assign to fighters**: respect fighter affinity on sources. For unaffiliated sources, round-robin by fighter priority.
5. **Execute**: fighters process assigned items in parallel (bounded by provider RPM limits).
6. **Fallback**: if a fighter fails on a source item, retry with its `fallback_fighter_id` (max 1 retry).
7. **Normalize**: normalizer LLM converts all raw fighter outputs to standard news item schema. Classifies, tags, and ranks.
8. **Assign to topics**: match each item's `tags` against board topic filters.
9. **Store**: persist normalized items to `board_news_item` table, run metadata to `board_run`.
10. **Publish**: if configured, push template HTML + `data.json` to GitHub Pages or export to local directory.

---

## Board

A board ties together: sources (from pool), fighters, normalizer, topics, schedule, and publish config.

### Properties

- **Source selection**: by tags, individual source IDs, or "all active"
- **Fighter selection**: pick from news fighters list (supports multiple fighters per board)
- **Normalizer config**: provider + model + instructions
- **Topics**: user-defined list with tag filter rules
- **Schedule**: cron expression (e.g., `0 */6 * * *` = every 6 hours)
- **Max news per run**: configurable, default 100
- **Max history**: runs to keep, default 10 (older runs pruned)
- **Template**: selected from bundled or user-custom templates
- **Publish target**: GitHub Pages, static export, or none

### Scheduling

- In-process scheduler (APScheduler or asyncio-based) running inside FastAPI lifespan
- Boards only run while the server is up
- Manual "Run Now" button for immediate execution
- Schedule toggle: active / paused

---

## Publishing

### GitHub Pages

- Push `index.html` (selected template) + `data.json` (latest board output) to a `gh-pages` branch of a configured GitHub repository
- Config: `{"repo": "user/my-news", "branch": "gh-pages"}`
- Requires `GH_TOKEN` with repo write access

### Static Export

- Generate `index.html` + `data.json` in a configurable local directory
- Config: `{"output_dir": "/path/to/output"}`
- Useful for serving via any static file server or embedding in other tools

---

## Templates

### Bundled Templates

Ship with 2 templates:
1. **Card Grid** — responsive grid of news item cards with title, summary, score badge, and tags
2. **News Feed List** — chronological feed with expandable summaries

### User-Custom Templates

- Drop HTML files in `~/.t01-llm-battle/templates/`
- Template is a single HTML+Alpine.js file that loads `data.json` via fetch
- Template receives the full board output JSON and renders it
- Auto-discovered at startup, appears in template picker

---

## System Defaults ("Works Immediately")

On first start, the system creates:

- **4 system sources**: HN Top Stories, TechCrunch RSS, AI/ML News (Serper), GitHub Trending
- **3 system fighters**: General News Summarizer, Tech Deep Dive, YouTube Analyzer
- **1 default board** ("Tech News Daily"):
  - All system sources
  - General News Summarizer fighter
  - Default normalizer (gemini-2.0-flash)
  - 3 default topics: "AI & ML", "Developer Tools", "Industry News"
  - Schedule: every 6 hours
  - Not active by default (user activates after adding API keys)

User workflow: add API keys → activate the default board → news starts flowing.

---

## Board UI

### Sidebar

New "Boards" section between Providers and Battles:
- Board list with name + last run time
- "+ New" button for board creation
- Active/paused indicator per board

### Board Creation Wizard

1. **Name & description**
2. **Select sources**: from pool by tags or individually
3. **Select fighters**: from news fighters list
4. **Configure normalizer**: provider + model + instructions (pre-filled default)
5. **Define topics**: name + tag filter rules
6. **Set schedule**: cron expression + max news per run
7. **Configure publish** (optional): GitHub Pages or static export

### Board View

- **Topic tabs**: "All" + user-defined topics
- **Topic page**: news items with dynamic tag filters, pagination, ranked by score
- **Sidebar**: run history list, "Run Now" button, schedule toggle, settings
- **Each item**: title, summary, source, score badge, tag chips, published date, source link
