# Roadmap

## v0.1 — Ship it (≤ 1 week from kick-off)

**Goal**: working tool, PyPI release, README, first GitHub stars.

| Area | Deliverable |
|------|-------------|
| CLI | `t01-llm-battle serve` starts server + opens browser |
| UI | Single-page Alpine.js app (battle creation, live run, results table) |
| Providers | LLM (via Pydantic AI): OpenAI, Anthropic, Google, Groq, OpenRouter, Ollama; Tool: Serper, Tavily, Firecrawl |
| Judge | LLM-as-judge (0–10 + reasoning, editable rubric, markdown report) |
| Persistence | SQLite (battles, sources, fighters, steps, runs, results, judgments, api_keys) |
| Distribution | `pipx install t01-llm-battle` on PyPI |
| Docs | README with elevator pitch, install, quickstart, provider setup |

## v0.2 — News & Trending Boards

**Goal**: personal news dashboards powered by fighter pipelines, with scheduled execution and publishing.

| Area | Deliverable |
|------|-------------|
| Source Pool | Global source management: CRUD, types (URL/RSS/API/social), tags, priority, max items, fighter affinity |
| News Fighters | Promote from battle, system prebuilts (General Summarizer, Tech Deep Dive, YouTube Analyzer), fallback chain |
| Load Balancing | Priority-ordered fetch, dedup, cap at max_news_per_run, affinity-based assignment, fallback on failure |
| Normalizer | Dedicated LLM step to standardize fighter output, classify, tag, and rank items (0–10) |
| Topics | User-defined categories with tag filter rules, dynamic filtering, "All" topic |
| Scheduler | In-process APScheduler, cron expressions, history retention with pruning |
| UI | Source management section, board creation wizard, topic pages with dynamic filters and pagination |
| Templates | 2 bundled (card grid, news feed list), user-custom support |
| Publishing | GitHub Pages push + static HTML/JSON export |
| System Defaults | 4 sources, 3 fighters, 1 board, 3 topics — works immediately after adding API keys |

See [08-news-boards.md](./08-news-boards.md) for the full spec.

## v0.3+ (future)

These are not committed. They exist to capture ideas without letting them bloat v0.2.

- Azure OpenAI + AWS Bedrock provider adapters
- Shareable result URLs (requires tiny hosted snapshot service)
- VS Code extension wrapper
- Multi-turn conversation support (system + user + assistant turns)
- Board publishing to Slack webhook, email digest, Obsidian vault
- Social media source providers (Twitter/X, Reddit, Bluesky)

## Explicit non-roadmap

The following will never be on the roadmap (see Non-Goals in `01-prd.md`):

- Accounts / auth / teams / SSO
- CI integration / regression tracking
- Dataset management beyond file/CSV upload
- Red teaming / guardrails / security scanning
- Cloud-hosted SaaS demo
- Monetization of any kind
