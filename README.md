# t01-llm-battle

**A tiny tool to help you pick the right approach for your AI project.**

[![PyPI version](https://img.shields.io/pypi/v/t01-llm-battle)](https://pypi.org/project/t01-llm-battle/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python >=3.11](https://img.shields.io/badge/python-%3E%3D3.11-blue)](https://www.python.org/)

---

## Install

Requires Python 3.11+.

```bash
pipx install t01-llm-battle
t01-llm-battle serve
```

Browser opens at `http://localhost:7878`. Ready in under 3 seconds.

---

## What it does

Run your real prompts against multiple LLMs or multi-step pipelines simultaneously, score each result with an LLM judge, and compare quality, cost, and latency side by side — all locally, no accounts, no cloud. Define **fighters** (a single model or a chained pipeline), upload your test cases as files or a CSV, press **Run**, and get a ranked markdown report you can share with your team.

![screenshot](docs/screenshot.png)

> (add real screenshot before v0.1 tag)

---

## Quickstart

1. `pipx install t01-llm-battle`
2. `t01-llm-battle serve` — starts the server and opens the browser
3. Open `http://localhost:7878` if the browser does not open automatically
4. Click **New Battle** — give it a name and set your judge config
5. **Add sources** — upload `.txt` / `.md` files or a `.csv` (one item per row)
6. **Add fighters** — pick a provider + model, or chain multiple steps into a pipeline
7. Click **Run** — watch step-level results appear live
8. Read the judge's ranked markdown summary and compare cost × quality × latency

---

## Providers supported

| Provider | Notes |
|----------|-------|
| OpenAI | GPT-4o, GPT-4o-mini, o1, o3-mini, … Supports `web_search` tool |
| Anthropic | Claude Opus, Sonnet, Haiku |
| Google Gemini | Gemini 2.0 Flash, Pro, … |
| Groq | Llama 3, Mixtral, … Fast inference |
| OpenRouter | Any model via OpenRouter — use any model slug |
| Ollama | Any local model, free, no API key needed — calls proxied via backend (CORS) |

Custom model IDs are always accepted; pricing shows as "unknown" for unlisted models.

### API keys

Set keys via environment variables:

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=...
export GROQ_API_KEY=...
export OPENROUTER_API_KEY=...
# Ollama — no key needed
```

Or enter them in the UI under **Settings → API Keys**. Keys are stored in a local SQLite database and never leave your machine. Environment variables always take precedence.

---

## Adding a custom provider

Drop a `.py` file in `~/.t01-llm-battle/providers/` and subclass `BaseProvider` (see `t01_llm_battle/providers/base.py`):

```python
from t01_llm_battle.providers.base import BaseProvider, ModelInfo, CompletionRequest, CompletionResult

class MyProvider(BaseProvider):
    name = "myprovider"
    display_name = "My Provider"
    models = [ModelInfo(id="my-model-v1", display_name="My Model v1")]

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        # call your API with request.messages, request.model_id, request.config
        ...
        return CompletionResult(output_text=..., input_tokens=..., output_tokens=..., latency_ms=...)
```

Restart `t01-llm-battle serve` — your provider appears in the model picker automatically.

---

## NOT list

t01-llm-battle is intentionally small. It will never have:

- Accounts, auth, teams, or SSO
- CI integration or regression tracking across runs
- Dataset management beyond file / CSV upload
- Red teaming, guardrails, or security scanning
- Custom scoring plugins, Python hooks, or YAML config
- Cloud-hosted SaaS or hosted demo instance
- Streaming responses (full responses only — ensures fair latency and token comparison)
- Cross-step memory beyond passing the previous step's output as input

This is the moat. If you need a full eval platform, see [Promptfoo](https://promptfoo.dev).

---

## License

MIT — free forever.
