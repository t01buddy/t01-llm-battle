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
| FR-14 | Results View | Side-by-side results: cost, latency, expandable step drill-down. When judge is configured, shows scores. When no judge, outputs shown side-by-side without scores. |
| FR-15 | SQLite Persistence | All battles, sources, fighters, steps, runs, results, judgments, api_keys |
| FR-16 | Custom Model IDs | Override catalog slugs; pricing shown as "unknown" |
| FR-19 | Provider Management UI | Sidebar footer link labelled "Providers"; lists providers with enable/disable toggle; edit popup for display name, API key, server URL (Ollama/LLM Studio/self-hosted); uninstall non-system providers |
| FR-20 | Sidebar Layout | Single page: left sidebar (app name, battle list, "Providers" footer link) + main content area (selected battle or default empty battle with 2 fighters) |

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

## Detail: FR-20 Sidebar Layout

- **Single page** with left sidebar (~260 px) + main content area (fills remaining width)
- **Sidebar contents**:
  - App name: "T01 LLM Battle"
  - Battle list: + New button; each entry shows name + created time + delete button; click name to load in main area
  - Providers section: list of providers with enable/disable toggle and edit button
- **Main area**: selected battle (Input / Definition / Result sections) or default empty battle (2 manual fighters) if none selected
- Sidebar collapses on narrow viewports

---

## Brand Theme (Paper Light)

Applies to FR-20 sidebar layout and all UI components. Paper-like aesthetic: warm off-white backgrounds, clean white cards, dark readable text.

| Token | Value |
|-------|-------|
| `bg.paper` | `#FAF9F6` (warm off-white / parchment) |
| `bg.card` | `#FFFFFF` (white with subtle shadow/border) |
| Primary accent | `#F0B90B` (gold — kept for contrast on light bg) |
| `text.high` | `#1a1a2e` (dark primary text) |
| `text.mid` | `#6b7280` (muted secondary text) |
| Borders | `#e5e5e5` (light gray) |
| Typography | system-ui stack, weight 600, `letter-spacing: -0.01em` |
| Sidebar bg | slightly tinted off-white or very light gray |

Replaces previous Gold-on-Ink dark theme (`#0d0f13` background, `#14181f` cards, `#E7ECF3` text).

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

- Side-by-side comparison of all fighters per source item
- Always shown: final output, total cost (USD), total latency (ms), expandable step drill-down
- **When judge is configured**: judge score (0–10) and reasoning displayed per fighter
- **When no judge is configured**: outputs displayed side-by-side without scores; users compare quality visually
- Judge scores column hidden when no judge is configured on the battle
