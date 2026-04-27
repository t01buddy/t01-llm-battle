# Data Models

## SQLite Schema

### `battle`

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| name | TEXT | User-given battle name |
| judge_provider | TEXT | Provider slug |
| judge_model | TEXT | Model slug |
| judge_rubric | TEXT | Full rubric prompt (user-editable) |
| created_at | TEXT | ISO-8601 |

---

### `battle_source`

One row per input item. All fighters receive the same set of source items.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| battle_id | TEXT FK | → battle.id |
| label | TEXT | Display name (filename or "Row 3") |
| content | TEXT | Full text content of the item |
| position | INTEGER | Display order |

---

### `fighter`

A named pipeline (one or more steps) or a manual entry.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| battle_id | TEXT FK | → battle.id |
| name | TEXT | User-given fighter name |
| is_manual | INTEGER | 1 = manual fighter, no steps |
| position | INTEGER | Display order |

---

### `fighter_step`

One row per step within a pipeline fighter. Steps are executed sequentially in `position` order.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| fighter_id | TEXT FK | → fighter.id |
| position | INTEGER | 1 = first step (receives source item) |
| system_prompt | TEXT | Nullable — omit to pass input as user message only |
| provider | TEXT | Provider slug |
| model_id | TEXT | Model slug (catalog or custom) |
| provider_config | TEXT | JSON: `{"temperature": 0.7, "tools": ["web_search"], ...}` |

> For tool provider steps, `provider_config` must include `"function"` (e.g. `"search"`, `"scrape"`). Token fields are null for tool steps; `cost_usd` reflects credits consumed.

---

### `run`

One execution of a battle.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| battle_id | TEXT FK | → battle.id |
| status | TEXT | `pending` / `running` / `complete` / `error` |
| started_at | TEXT | ISO-8601 |
| finished_at | TEXT | ISO-8601, nullable |

---

### `step_result`

One row per (run × fighter × step × source item). Stores intermediate step I/O.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| run_id | TEXT FK | → run.id |
| fighter_id | TEXT FK | → fighter.id |
| step_id | TEXT FK | → fighter_step.id |
| source_id | TEXT FK | → battle_source.id |
| input_text | TEXT | Text fed into this step (source content or previous step output) |
| output_text | TEXT | Full model response; nullable if error |
| input_tokens | INTEGER | Nullable (null for tool provider steps) |
| output_tokens | INTEGER | Nullable (null for tool provider steps) |
| latency_ms | INTEGER | Nullable |
| cost_usd | REAL | Nullable (unknown for custom models). For tool providers, reflects credits consumed converted to USD. |
| error | TEXT | Nullable — error message if the step failed |
| created_at | TEXT | ISO-8601 |

---

### `fighter_result`

One row per (run × fighter × source item). Aggregates step results and stores the judgment.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| run_id | TEXT FK | → run.id |
| fighter_id | TEXT FK | → fighter.id |
| source_id | TEXT FK | → battle_source.id |
| final_output | TEXT | Last step's output (automated) or user-entered text (manual) |
| total_cost_usd | REAL | Sum of step costs; nullable |
| total_latency_ms | INTEGER | Sum of step latencies; nullable |
| total_input_tokens | INTEGER | Sum across steps; nullable |
| total_output_tokens | INTEGER | Sum across steps; nullable |
| status | TEXT | `pending` / `running` / `awaiting_input` / `complete` / `error` |
| judge_score | REAL | 0–10, nullable until judged |
| judge_reasoning | TEXT | Nullable until judged |
| created_at | TEXT | ISO-8601 |

> `awaiting_input` is used exclusively for manual fighters.

---

### `api_key`

| Column | Type | Notes |
|--------|------|-------|
| provider | TEXT PK | Provider slug |
| display_name | TEXT | Optional human-readable label; defaults to provider slug if NULL |
| key_value | TEXT | Encrypted at rest (local machine only). Used by both LLM and tool providers (Serper, Tavily, Firecrawl). |
| server_url | TEXT | Optional base URL for self-hosted providers (Ollama, LLM Studio, OpenAI-compatible). NULL for cloud providers. |
| updated_at | TEXT | ISO-8601 |

> Env vars (e.g. `OPENAI_API_KEY`) always override `key_value` at runtime. `server_url` is used when the provider requires a custom endpoint (Ollama default: `http://localhost:11434`).

---

## Entity Relationships (v0.1 — Battles)

```
battle
  ├── battle_source (1..N)
  ├── fighter (1..N)
  │     └── fighter_step (0..N)  [0 if is_manual]
  └── run (1..N)
        └── fighter_result (fighter × source)
              └── step_result (step × source)  [empty if is_manual]
```

---

## v0.2 — News & Trending Boards

### `news_source`

Global pool of data sources for news boards.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| name | TEXT | Display name |
| source_type | TEXT | `url` / `rss` / `api` / `social` |
| config | TEXT | JSON: type-specific fetch config |
| tags | TEXT | JSON array of tag strings |
| priority | INTEGER | 1 = highest, controls fetch order |
| max_items | INTEGER | Max items per fetch (default 5) |
| fighter_affinity | TEXT | JSON array of news_fighter IDs (empty = any fighter) |
| is_system | INTEGER | 1 = shipped with product, cannot be deleted |
| status | TEXT | `active` / `paused` / `error` |
| last_error | TEXT | Nullable — last fetch error message |
| created_at | TEXT | ISO-8601 |

---

### `news_fighter`

Fighters available for news processing. References existing fighter entities.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| fighter_id | TEXT FK | → fighter.id (reuses existing fighter + steps) |
| name | TEXT | Display name (may differ from source fighter) |
| fallback_fighter_id | TEXT FK | → news_fighter.id, nullable — retry with this on failure |
| priority | INTEGER | 1 = highest, for load balancing |
| is_system | INTEGER | 1 = shipped with product |
| created_at | TEXT | ISO-8601 |

---

### `board`

A personal news/info dashboard.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| name | TEXT | Board name |
| description | TEXT | Optional |
| source_filter | TEXT | JSON: `{"tags": ["ai"], "source_ids": ["..."]}` |
| fighter_ids | TEXT | JSON array of news_fighter IDs |
| normalizer_provider | TEXT | Provider slug for normalizer LLM |
| normalizer_model | TEXT | Model slug for normalizer |
| normalizer_instructions | TEXT | System prompt for normalizer (editable) |
| schedule_cron | TEXT | Cron expression (e.g., `0 */6 * * *`) |
| max_news_per_run | INTEGER | Default 100 |
| max_history | INTEGER | Runs to keep (default 10), older pruned |
| is_active | INTEGER | 1 = scheduler runs this board |
| template_id | TEXT | Template filename |
| publish_target | TEXT | `github_pages` / `static` / NULL |
| publish_config | TEXT | JSON config for publish target |
| is_system | INTEGER | 1 = shipped with product |
| created_at | TEXT | ISO-8601 |

---

### `board_topic`

User-defined categories for organizing news within a board.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| board_id | TEXT FK | → board.id |
| name | TEXT | Topic name (e.g., "AI & ML") |
| description | TEXT | Optional |
| tag_filter | TEXT | JSON: `{"include": ["ai", "ml"], "exclude": ["spam"]}` |
| position | INTEGER | Display order |

> The built-in "All" topic is not stored — it is implicit and always shows all items ranked by relevance.

---

### `board_run`

One execution of a board's news pipeline.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| board_id | TEXT FK | → board.id |
| status | TEXT | `pending` / `running` / `complete` / `error` |
| items_fetched | INTEGER | Raw items before dedup |
| items_processed | INTEGER | After dedup + cap |
| cost_usd | REAL | Total cost of this run |
| started_at | TEXT | ISO-8601 |
| finished_at | TEXT | ISO-8601, nullable |

---

### `board_news_item`

Normalized news items, one row per item per run.

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | UUID |
| run_id | TEXT FK | → board_run.id |
| board_id | TEXT FK | → board.id |
| title | TEXT | Normalized title |
| summary | TEXT | Normalized summary |
| source_url | TEXT | Original URL |
| source_name | TEXT | Source display name |
| fighter_name | TEXT | Fighter that processed this item |
| category | TEXT | Primary category |
| tags | TEXT | JSON array of tag/label strings |
| relevance_score | REAL | 0–10, assigned by normalizer |
| published_at | TEXT | Original publish date |
| created_at | TEXT | ISO-8601 |

---

### `board_seen_item`

Deduplication tracking. Prevents re-processing items across runs.

| Column | Type | Notes |
|--------|------|-------|
| board_id | TEXT | → board.id |
| item_hash | TEXT | SHA-256 of URL + title |
| first_seen_at | TEXT | ISO-8601 |
| PK | | (board_id, item_hash) |

---

## Entity Relationships (v0.2 — Boards)

```
news_source (global pool)
  └── fighter_affinity → news_fighter (optional, many-to-many via JSON)

news_fighter
  ├── fighter_id → fighter (reuses battle fighter + steps)
  └── fallback_fighter_id → news_fighter (self-referential)

board
  ├── source_filter → news_source (by tags or IDs, via JSON)
  ├── fighter_ids → news_fighter (multiple, via JSON)
  ├── board_topic (1..N)
  ├── board_run (0..N)
  │     └── board_news_item (0..N)
  └── board_seen_item (0..N)
```
