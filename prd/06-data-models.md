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

## Entity Relationships

```
battle
  ├── battle_source (1..N)
  ├── fighter (1..N)
  │     └── fighter_step (0..N)  [0 if is_manual]
  └── run (1..N)
        └── fighter_result (fighter × source)
              └── step_result (step × source)  [empty if is_manual]
```
