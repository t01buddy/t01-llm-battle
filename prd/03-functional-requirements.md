# Functional Requirements

| # | Area | Summary |
|---|------|---------|
| FR-1 | CLI & Server | `t01-llm-battle serve` starts FastAPI on port 7979, opens browser |
| FR-2 | Battle Creation | Name, sources, fighters (multi-step pipelines or manual), judge config (optional) |
| FR-3 | Sources | Upload text/md files or a CSV; each file or CSV row = one input item |
| FR-4 | Fighters & Steps | Named pipelines; each step has system prompt, provider, model, config |
| FR-5 | Manual Fighter | No steps; user enters result per source item during a run |
| FR-6 | Provider Adapters | LLM (via Pydantic AI): OpenAI, Anthropic, Google, Groq, OpenRouter, Ollama, LLM Studio; Tool (httpx): Serper (search/scrape), Tavily (search), Firecrawl (scrape/crawl) |
| FR-7 | Provider Config | Per-step: temperature, max_tokens, function (for tool providers, e.g. `serper:search`), etc. |
| FR-17 | Provider Types | Each provider has a type (LLM or TOOL); LLM providers use token-based pricing; tool providers use credit-based pricing |
| FR-18 | Pricing Models | Token-based (LLM): input/output $/1M tokens; credit-based (TOOL): fixed cost per function call. Provider calculates and reports usage after each run |
| FR-8 | Provider Management | Per-provider config: display name (optional, defaults to provider slug), API key, server URL / base URL (optional, for Ollama, LLM Studio, self-hosted); stored in SQLite; env vars override key at runtime; API key masked in UI |
| FR-9 | Rate Limiting | Per-provider RPM throttling with bounded concurrency |
| FR-10 | Run Execution | Parallel across fighters × sources; sequential within a fighter's steps |
| FR-11 | Live Run View | Polling UI; step-level status per fighter per source item |
| FR-12 | LLM-as-Judge | Optional. When configured, scores final step output per fighter per source (0–10 + reasoning). When not configured, run completes without scoring. |
| FR-13 | Markdown Report | Judge generates a markdown summary; rendered in browser via marked.js |
| FR-14 | Results View | Fighter summary leaderboard table (rank, avg score, cost, tokens, time) + per-source breakdown with expandable output. When no judge, outputs shown without scores. See [09-ui-redesign.md](./09-ui-redesign.md). |
| FR-15 | SQLite Persistence | All battles, sources, fighters, steps, runs, results, judgments, api_keys |
| FR-16 | Custom Model IDs | Override catalog slugs; pricing shown as "unknown" |
| FR-19 | Provider Management UI | Modal overlay (opened from sidebar icon); lists LLM and tool providers with enable/disable toggle, key status, edit form for API key, display name, server URL; pricing refresh button; uninstall non-system providers |
| FR-20 | App Layout | 3-column layout: collapsible icon rail sidebar (64px) + tabbed main content (Setup/Run/Results) + right rail battle list (320px). See [09-ui-redesign.md](./09-ui-redesign.md) for mockups. |

### v0.2 — News & Trending Boards

| # | Area | Summary |
|---|------|---------|
| FR-21 | Source Pool | Global data source management: CRUD, types (URL/RSS/API/social), tags, priority, max items per source, fighter affinity, status |
| FR-22 | News Fighters | Promote battle fighters to news fighters list; system prebuilts; fallback chain; priority for load balancing |
| FR-23 | Load Balancing | Priority-ordered fetch, dedup by URL+title hash, cap at max_news_per_run (default 100), affinity-based assignment, fallback on failure |
| FR-24 | Normalizer | Dedicated LLM step to convert raw fighter output to standard news item schema; classify, tag, and rank items (0–10) |
| FR-25 | Topics | User-defined categories with tag filter rules; dynamic tag-based filtering; built-in "All" topic |
| FR-26 | Board Creation | Source selection (by tags/IDs), fighter selection, normalizer config, topics, schedule, max news per run |
| FR-27 | Scheduled Execution | In-process cron (APScheduler), dedup by URL+title hash, history retention with pruning |
| FR-28 | Output & Templates | Standard JSON schema for news items; 2 bundled templates (card grid, news list); user-custom templates |
| FR-29 | Publishing | GitHub Pages push (template HTML + data.json) + static HTML/JSON export to local directory |
| FR-30 | Source Management UI | Dedicated section: CRUD, type-specific config forms, tags, priority, affinity, health status |
| FR-31 | Topic Pages UI | Topic detail page with dynamic tag filters, pagination (default 20 items), ranked by relevance score |
| FR-32 | System Defaults | Ship with 4 system sources, 3 system fighters, 1 default board with 3 topics — works immediately after adding API keys |
| FR-33 | Fighter Promotion | "Add to News Fighters" action on battle fighter cards; copies fighter + steps independently |

---

## Detail: FR-8 Provider Management

- **Display name**: optional label shown in the UI; defaults to provider slug if blank
- **API key**: stored encrypted in SQLite; env var `<PROVIDER>_API_KEY` always overrides at runtime; masked in UI
- **Server URL / Base URL**: optional; used by Ollama, LLM Studio, and self-hosted OpenAI-compatible endpoints

---

## Detail: FR-19 Provider Management UI

- **Sidebar footer link**: labelled "Providers" (previously "API Keys")
- **Provider list**: name, enabled/disabled toggle, edit button
- **Edit popup**: display name field, API key field, server URL field (Ollama/LLM Studio/self-hosted only), uninstall button (non-system providers only)
- System providers (built-in) cannot be uninstalled; uninstall returns 403
- Provider config (enabled state, display name, server URL) stored in SQLite alongside API keys
- Disabled providers are excluded from fighter step provider dropdowns

---

## Detail: FR-20 App Layout

- **3-column layout**: icon rail sidebar (64px collapsible) + main content area (flex: 1) + right rail battle list (~320px)
- **Icon rail sidebar**: brand icon, navigation icons (Battles, Providers, Settings), collapse toggle. Providers opens a modal overlay.
- **Main content**: topbar (battle name + run ID) + tab bar (Setup / Run / Results) + active tab content
- **Right rail**: battle list with active highlighting, status tags (new/done), "+ New" button
- **Responsive**: sidebar collapses to icons on narrow viewports; right rail hides on mobile (<1100px)
- See [09-ui-redesign.md](./09-ui-redesign.md) for full mockups

---

## Brand Theme (Paper)

Applies to all UI components. Paper-like editorial aesthetic with serif display font.

| Token | Value |
|-------|-------|
| `bg.paper` | `#FAF9F6` (warm off-white / parchment) |
| `bg.card` | `#FFFFFF` (white with subtle shadow) |
| Primary accent | `#D4A02A` (warm gold) |
| `text.high` | `#1a1a2e` (dark primary text) |
| `text.mid` | `#6b7280` (muted secondary text) |
| Borders | `#e5e5e5` (light gray) |
| Display font | `"Fraunces", serif` (headings, battle names, scores) |
| Body font | `"Inter", system-ui, sans-serif` (content, labels) |
| Mono font | `"JetBrains Mono", monospace` (metadata, IDs, costs) |

CSS architecture: all component classes use `.ba-*` prefix (battle-app). Framework-agnostic, works directly with Alpine.js.

---

## Detail: FR-2 Battle Creation

- **Name**: free text
- **Sources**: see FR-3
- **Fighters**: add one or more; each has a name and is either a pipeline (FR-4) or manual (FR-5)
- **Judge config**: **optional** — provider + model + rubric (pre-filled default, fully editable EasyMDE). If omitted, results are displayed without scoring.

---

## Detail: FR-3 Sources

- **Text/markdown files**: upload one or more `.txt` / `.md` files — each file becomes one source item
- **CSV file**: upload a single CSV — each data row becomes one source item; first column is used as the input text (or user selects column)
- Source items are stored in SQLite and reused across runs of the same battle
- All fighters receive the same set of source items

---

## Detail: FR-4 Fighters & Steps

A **fighter** is a named pipeline of one or more steps:

```
Source item
    ↓
  Step 1  [system prompt (opt)] [provider] [model] [config]
    ↓ output
  Step 2  [system prompt (opt)] [provider] [model] [config]
    ↓ output
  Step N  ...
    ↓ final output  →  sent to judge
```

- **Step input**: step 1 receives the source item text; step N (N > 1) receives the full output text of step N-1
- **System prompt**: optional; if omitted the step passes the input straight to the model as a user message
- **Provider + model**: any registered provider and model ID (catalog or custom)
- **Provider config** (FR-7): JSON object stored per step; merged with defaults at call time
- Steps are ordered and displayed in creation order; reordering supported via drag or up/down buttons

---

## Detail: FR-5 Manual Fighter

- No steps defined
- When a run starts, each source item shows an empty text area for the user to enter a result
- Manual results can be submitted one at a time as the user works through inputs
- Once all manual results are submitted, they are sent to the judge alongside automated fighters
- Manual fighters are useful for: human baseline, pre-existing results, or copy-pasting outputs from external tools

---

## Detail: FR-7 Provider Config

Each step stores a `provider_config` JSON object. Supported keys:

| Key | Type | Notes |
|-----|------|-------|
| `temperature` | float | 0.0–2.0; provider default if omitted (LLM only) |
| `max_tokens` | int | Provider default if omitted (LLM only) |
| `tools` | list[str] | Tool slugs to enable (e.g. `["web_search"]` for OpenAI) |
| `top_p` | float | Optional nucleus sampling (LLM only) |
| `system_prompt_role` | str | `"system"` (default) or `"developer"` (OpenAI o-series) |
| `function` | str | Function to invoke for tool providers (e.g. `"search"`, `"scrape"` for Serper/Firecrawl) |

Unknown keys are passed through to the provider as-is — forward-compatible with new provider options.

---

## Detail: FR-10 Run Execution

- All fighters run in parallel (bounded by per-provider RPM limits)
- Within a single fighter, steps are **sequential**: step N waits for step N-1 to complete
- A fighter's run for a source item fails gracefully if any step errors — error stored, remaining steps skipped, judgment skipped for that fighter × source pair
- Manual fighters do not run automatically; they enter `awaiting_input` status

---

## Detail: FR-12 LLM-as-Judge

- **Optional**: if no judge is configured on the battle, the run completes without scoring
- Judges the **final step output** of each fighter per source item
- Default rubric covers: relevance, accuracy, conciseness, helpfulness
- Score 0–10 with written reasoning
- Tolerant parser handles JSON wrapped in markdown fences
- User can fully replace the rubric — no locked-in scoring logic
- Score AND reasoning shown so users can sanity-check judge bias
- Manual fighter results are judged the same way as automated results

---

## Detail: FR-13 Markdown Report

- After all fighters are judged, the judge model is prompted to generate a **markdown summary report**
- Report includes: rankings, per-fighter score summary, notable observations, cost + latency comparison
- Rendered in the browser via `marked.js`
- User can copy raw markdown or print via browser
- Only generated when a judge is configured; skipped otherwise

---

## Detail: FR-14 Results View

- **Fighter Summary**: leaderboard table showing rank, fighter name, avg score, total cost, token count, latency, success/fail counts
- **Per-Source Breakdown**: expandable cards per source item showing each fighter's output, score, cost, and tokens side-by-side
- "Show output" toggle per fighter result to expand/collapse full output text
- **When judge is configured**: scores shown in leaderboard and per-source cards
- **When no judge is configured**: outputs shown without scores; users compare quality visually
- Download Markdown button for judge report
