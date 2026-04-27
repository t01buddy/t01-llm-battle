# Product Requirements Document (PRD)

## t01-llm-battle — Local LLM Battle Arena

**Version**: 0.1
**Date**: 2026-04-16
**Status**: Draft
**Owner**: t01buddy (OSS, MIT)

## Vision

A tiny, local tool that helps a developer answer one question at the start of a project: **"Which approach should I use for this job?"**

The user runs a CLI, opens a browser, defines a "battle" — a set of source inputs (text/markdown files or a CSV) and a list of **fighters**, each representing a different approach. A fighter is a pipeline of one or more steps: the output of each step feeds into the next, with the first step receiving source inputs. Steps can use LLM providers (OpenAI, Anthropic, etc.) or non-LLM tool providers (Serper search/scrape, Tavily search, Firecrawl scraping). Fighters can also be manual: the user enters results by hand, enabling human-vs-AI or baseline comparisons.

After running, the final output of each fighter is judged side-by-side: quality score, cost, latency, token usage. No accounts, no cloud, no SaaS. Keys live on the developer's machine.

### Positioning

| Aspect | t01-llm-battle | Promptfoo (incumbent) |
|--------|----------------|-----------------------|
| Primary job-to-be-done | Pipeline & model comparison at project start | Ongoing prompt regression testing |
| Setup | `pipx install t01-llm-battle && t01-llm-battle serve` → browser opens | YAML config, CLI invocation |
| Surface | Single-page web UI, in-browser | CLI-first, artifacts-only |
| Sharing | Markdown report (copy/print) | Local artifacts |
| Cost model | Free forever (OSS) | OSS core + paid Enterprise tier |
| Scope | Deliberately small, no teams/CI | Full eval platform, red team, SSO, teams |

**We are not trying to beat Promptfoo.** We are taking one slice of its surface (pick-the-right-approach-now) and making it a dead-simple standalone tool.

### Target Users

| User | Primary intent | Success criteria |
|------|----------------|------------------|
| Senior developer evaluating models for a new feature | "Is Haiku good enough or do I need Sonnet?" | Can decide in < 10 minutes with confidence |
| AI engineer comparing pipelines vs single models | "Does my two-step extraction pipeline actually beat a single call?" | Sees cost × latency × quality on same axes |
| LLM beginner learning the ecosystem | "What do different models actually do differently?" | Understands tradeoffs from one shareable report |

## Document Index

| File | Description |
|------|-------------|
| [01-prd.md](./01-prd.md) | This document — vision, positioning, scope |
| [02-tech-stack.md](./02-tech-stack.md) | Architecture, tech choices, project layout |
| [03-functional-requirements.md](./03-functional-requirements.md) | FRs grouped by feature area |
| [04-non-functional-requirements.md](./04-non-functional-requirements.md) | Performance, privacy, packaging |
| [05-user-stories.md](./05-user-stories.md) | Key workflows |
| [06-data-models.md](./06-data-models.md) | SQLite schema: battle / source / fighter / step / run / result / judgment / api_key |
| [07-roadmap.md](./07-roadmap.md) | Phased delivery plan |
| [09-ui-redesign.md](./09-ui-redesign.md) | UI redesign — 3-column layout, Paper theme, tabbed content, mockups |

## v0.1 Scope

**In scope**

- CLI that starts a local FastAPI server on a configurable port (default 7878) and opens the browser
- Single-page web UI (Alpine.js, no build step): sidebar layout with battle list + provider management on the left, battle detail on the right; Paper Light brand theme
- **Battle creation**:
  - Name + judge config (provider, model, rubric)
  - **Sources**: upload text/markdown files (one item per file) OR a CSV file (one item per row)
  - **Fighters**: one or more named pipelines, each with:
    - One or more **steps**: system prompt (optional), provider, model ID, provider config (temperature, tools, etc.)
    - Step N input = step N-1 output; step 1 input = source item
    - OR **manual fighter**: no steps — user enters result per source item after run starts
- Provider adapters: **LLM (via Pydantic AI): OpenAI, Anthropic, Google, Groq, OpenRouter, Ollama; Tool: Serper, Tavily, Firecrawl**
- Per-provider RPM throttling with bounded concurrency
- LLM-as-judge scoring (0–10 + reasoning, user-editable rubric, tolerant JSON parsing) on final step output
- SQLite persistence (battles, sources, fighters, steps, runs, results, judgments, api_keys)
- API keys in env vars OR entered in UI and stored in local SQLite (env wins)
- Live run view with polling, step-level drill-down per fighter per source item
- Judge generates a markdown summary report rendered in the browser
- MIT license, GitHub repo under `t01buddy` org

**Explicitly out of scope (v0.1) — the "NOT list" is the moat**

- Accounts, auth, teams, SSO
- CI integration, regression tracking across runs
- Dataset management beyond file/CSV upload
- Red teaming, security scanning, guardrails
- Custom scoring plugins, Python hooks, YAML config
- Self-hosted deployment docs beyond a Dockerfile
- Cloud-hosted demo instance (distribution via `pipx`, not hosted SaaS)
- Streaming responses (we wait for full responses to ensure fair latency + token comparison)
- Cross-step memory or context beyond passing the previous step's output as input

## Key Success Metrics

| Metric | Target | Rationale |
|--------|--------|-----------|
| Time from `pipx install` to first result | < 2 minutes | "Small + helpful" is a lie if setup is slow |
| GitHub stars at 30 days post-launch | 500 | Signal for dev mindshare |
| Weekly active installs at 90 days | 1,000 | Real usage, not launch spike |
| Install size (wheels + deps) | < 15 MB | Matches the "small" ethos |
| Cold start to UI ready | < 3 seconds | Equivalent to `npx promptfoo init` |
| Providers supported at launch | 9 (6 LLM + 3 tool) | Matches v0.1 scope |

## Architecture Principles

| Principle | Consequence |
|-----------|-------------|
| **Keys in browser → provider direct** | No server-side proxy of API calls. Zero infra cost, zero liability, no abuse handling. Exception: local Ollama calls go through the Python backend (CORS). |
| **One process, one file** | FastAPI + asyncio event loop + SQLite in one Python process. No Celery, Redis, or worker pool. |
| **Bring-your-own-keys, stored locally** | Env vars or SQLite. Keys never leave the user's machine. |
| **Provider adapters use appropriate abstractions** | LLM providers use Pydantic AI as a unified abstraction layer (tool-calling, structured output, model switching). Tool providers (Serper, Tavily, Firecrawl) remain thin `httpx` clients — no SDK needed. Adding a provider is one file. |
| **Custom model IDs always allowed** | Curated model catalog is a starting point; users can enter any model slug. Pricing is just "unknown" for custom models. Tool ages well when providers ship new models. |
| **No streaming in v0.1** | We need full responses to compare final token counts and latency apples-to-apples. Streaming adds complexity and asymmetric UX. |

## Non-Goals

- Replacing Promptfoo.
- Monetizing the tool. It stays free and small forever.
- Becoming a platform. Feature requests that point toward "SaaS", "teams", "CI", or "enterprise" are explicit nos.
- Scoring objectivity. LLM-as-judge is acknowledged as subjective. We do not claim to produce authoritative benchmarks.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Promptfoo adds a comparable web UI and closes the gap | Medium | High | Stay smaller. Our moat is the "NOT list"; feature creep kills it. |
| Provider ToS disallow publishing comparative outputs | Low | Medium | Tool never publishes results centrally. All reports live on the user's machine; they share them voluntarily. |
| Model catalog / pricing goes stale | High | Low | Custom model IDs bypass the catalog. Community PRs update pricing. Never promise "latest model list". |
| LLM-as-judge bias (same-family scoring, verbosity bias) | High | Medium | Let user pick any judge model + fully edit the rubric. Show score AND reasoning so users can sanity-check. |
| Key leakage via user misconfiguration | Low | High | Never log keys. `.env` in `.gitignore`. UI masks keys. |

## Open Questions

- Should v0.1 ship a public hosted demo, or keep distribution purely `pipx`?
- Do we want shareable result URLs in v0.1 (requires a tiny hosted snapshot service), or defer to v0.2?
- Do we add Azure OpenAI and AWS Bedrock as providers in v0.1, or wait for user demand?
- Do we ship a VS Code extension wrapper in v0.2 for in-editor battles?

## Appendix: Naming & Brand

- **Package / CLI / repo**: `t01-llm-battle`
- **Repo path**: `github.com/t01buddy/t01-llm-battle`
- **Install**: `pipx install t01-llm-battle` → `t01-llm-battle serve`
- **License**: MIT
- **Elevator pitch (README top line)**: *"A tiny tool to help you pick the right approach for your AI project. Define fighters — single models or multi-step pipelines — run them against your real inputs, and see quality, cost, and latency side by side. No accounts, no cloud, runs in your browser."*
