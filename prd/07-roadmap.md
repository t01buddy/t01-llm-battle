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

## v0.2+ (future)

These are not committed. They exist to capture ideas without letting them bloat v0.1.

- Azure OpenAI + AWS Bedrock provider adapters
- Shareable result URLs (requires tiny hosted snapshot service)
- VS Code extension wrapper
- Model catalog community PRs + pricing refresh automation
- Multi-turn conversation support (system + user + assistant turns)

## Explicit non-roadmap

The following will never be on the roadmap (see Non-Goals in `01-prd.md`):

- Accounts / auth / teams / SSO
- CI integration / regression tracking
- Dataset management beyond file/CSV upload
- Red teaming / guardrails / security scanning
- Cloud-hosted SaaS demo
- Monetization of any kind
