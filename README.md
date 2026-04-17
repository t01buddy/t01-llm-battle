# t01-llm-battle

**A tiny tool to help you pick the right approach for your AI project.**

Define fighters — single models or multi-step pipelines — run them against your real inputs, and see quality, cost, and latency side by side. No accounts, no cloud, runs in your browser.

```
pipx install t01-llm-battle
t01-llm-battle serve
```

Browser opens at `http://localhost:7878`. Ready in under 3 seconds.

---

## What it does

You define a **battle**:

- **Sources** — your real test cases: upload `.txt` / `.md` files (one per item) or a `.csv` (one row per item)
- **Fighters** — the approaches you want to compare:
  - A single model with a system prompt
  - A multi-step pipeline where each step's output feeds the next
  - A manual fighter where you enter results by hand (human baseline)
- **Judge** — an LLM that scores each fighter's final output (0–10 + reasoning)

Press **Run**. Watch results appear live. Read the judge's markdown summary.

---

## Example: does chaining prompts actually help?

| Fighter | Steps |
|---------|-------|
| **Baseline** | GPT-4o-mini, single prompt |
| **Pipeline** | Haiku → extract facts → GPT-4o-mini → write answer |
| **Human** | You type the answer |

Upload 10 test cases as a CSV. Run. See if the pipeline's quality gain justifies its extra cost.

---

## Features

- **Multi-step pipelines** — chain any providers in any order; each step gets the previous step's output
- **Manual fighters** — enter results by hand to create a human baseline
- **Flexible sources** — text files, markdown files, or CSV rows
- **Per-step config** — temperature, tools (e.g. OpenAI `web_search`), max_tokens, and more
- **6 providers out of the box** — OpenAI, Anthropic, Google, Groq, OpenRouter, Ollama
- **Custom providers** — drop a `.py` file in `~/.t01-llm-battle/providers/`, subclass `BaseProvider`, done
- **LLM-as-judge** — fully editable rubric; score + reasoning shown so you can sanity-check bias
- **Markdown report** — judge generates a ranked summary; copy or print from the browser
- **Live run view** — step-level status updates as each call completes
- **Bring your own keys** — set env vars or enter keys in the UI; stored locally in SQLite, never sent anywhere

---

## Install

Requires Python 3.11+.

```bash
pipx install t01-llm-battle
```

Or with pip:

```bash
pip install t01-llm-battle
```

---

## Usage

```bash
# Start the server (opens browser automatically)
t01-llm-battle serve

# Use a different port
t01-llm-battle serve --port 8080

# Don't open the browser automatically
t01-llm-battle serve --no-open
```

---

## API Keys

Set keys via environment variables (recommended):

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=...
export GROQ_API_KEY=...
export OPENROUTER_API_KEY=...
# Ollama runs locally — no key needed
```

Or enter them directly in the UI under **Settings → API Keys**. Keys are stored in a local SQLite database and never leave your machine. Environment variables always take precedence.

---

## Custom Providers

Create `~/.t01-llm-battle/providers/myprovider.py`:

```python
from t01_llm_battle.providers.base import BaseProvider, ModelInfo, CompletionRequest, CompletionResult

class MyProvider(BaseProvider):
    name = "myprovider"
    display_name = "My Provider"
    models = [
        ModelInfo(id="my-model-v1", display_name="My Model v1"),
    ]

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        # call your API with request.messages, request.model_id, request.config
        ...
        return CompletionResult(
            output_text=response_text,
            input_tokens=usage.input,
            output_tokens=usage.output,
            latency_ms=elapsed_ms,
        )
```

Restart `t01-llm-battle serve` — your provider appears in the model picker.

---

## Providers

| Provider | Models | Notes |
|----------|--------|-------|
| OpenAI | GPT-4o, GPT-4o-mini, o1, o3-mini, … | Supports `web_search` tool |
| Anthropic | Claude Opus, Sonnet, Haiku | |
| Google | Gemini 2.0 Flash, Pro, … | |
| Groq | Llama 3, Mixtral, … | Fast inference |
| OpenRouter | Any model via OpenRouter | Use any model slug |
| Ollama | Any local model | Calls via backend (CORS) |

Custom model IDs always accepted — pricing shows as "unknown" for unlisted models.

---

## Not in scope

t01-llm-battle is intentionally small. It will never have:

- Accounts, auth, teams, or SSO
- CI integration or regression tracking across runs
- Cloud-hosted SaaS or hosted demo
- Red teaming, guardrails, or security scanning
- Streaming responses (full responses only for fair latency comparison)

This is the moat. If you need a full eval platform, see [Promptfoo](https://promptfoo.dev).

---

## License

MIT — free forever.
