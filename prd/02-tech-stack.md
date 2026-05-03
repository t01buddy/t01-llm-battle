# Tech Stack & Architecture

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| CLI | **Typer** | Type-hint-based, modern DX, tiny (0.05 MB), built on Click |
| ASGI server | **FastAPI + uvicorn** | Async-first, single process, built-in CORS/OpenAPI, ~0.6 MB |
| Async HTTP | **httpx** | No SDK dependencies per provider, async, 0.07 MB |
| Database | **SQLite (built-in) + aiosqlite** | Zero-config, WAL mode, async-safe |
| Frontend | **Alpine.js 3.x** (bundled in wheel) | No build step, 15 KB, directive-based reactive UI |
| Markdown render | **marked.js** (bundled in wheel) | Render LLM responses + judge report via `marked.parse()` → `x-html` |
| Markdown editor | **EasyMDE** (bundled in wheel) | Rich editor for system prompt + judge rubric; split write/preview |
| LLM abstraction | **pydantic-ai** | Unified model interface across LLM providers; tool-calling, structured output |
| Plugin system | **Folder-based + BaseProvider ABC** | Drop a `.py` file in `~/.t01-llm-battle/providers/` — no packaging required |

**Estimated install size**: ~10–12 MB (well under 15 MB target).

## Report Approach

No HTML generation. After a run completes, the judge model is prompted to produce a **markdown summary report** (rankings, scores, per-fighter observations). `marked.js` renders it in the browser. Users copy the raw markdown or print via the browser.

## Architecture Principles

See `01-prd.md` → Architecture Principles for the full list. Key constraints:

- **One process**: FastAPI + asyncio + SQLite in one Python process. No Celery, Redis, or worker pool.
- **Keys in browser → provider direct**: No server-side proxy of API calls (exception: Ollama and LLM Studio require CORS bypass via backend).
- **No streaming in v0.1**: Full responses only for fair latency/token comparison.
- **Pydantic AI for LLM providers**: `pydantic-ai` is the unified abstraction layer for all LLM providers — tool-calling, structured output, and model switching without SDK churn. Tool providers (Serper, Tavily, Firecrawl) use plain `httpx` — no SDK needed.

## Plugin Architecture

### BaseProvider ABC (`t01_llm_battle/providers/base.py`)

```python
class ProviderType(Enum):
    LLM = "llm"   # uses Pydantic AI; token-based pricing
    TOOL = "tool" # httpx client; credit-based pricing

class BaseProvider(ABC):
    name: str           # e.g. "openai"
    display_name: str   # e.g. "OpenAI"
    provider_type: ProviderType
    models: list[ModelInfo]  # curated catalog; custom IDs always accepted

    @abstractmethod
    async def run(self, request: ProviderRequest) -> ProviderResult:
        ...

    @abstractmethod
    def estimate_cost(self, result: ProviderResult) -> float | None:
        """Token-based (LLM) or credit-based (tool) cost in USD."""
        ...
```

### Discovery at startup

1. Load built-in providers from `t01_llm_battle/providers/` (importlib)
2. Scan `~/.t01-llm-battle/providers/` for `*.py` files
3. Load each via `importlib.util.spec_from_file_location()`
4. Register any class that subclasses `BaseProvider`

### Adding a custom provider (user workflow)

1. Create `~/.t01-llm-battle/providers/myprovider.py`
2. Subclass `BaseProvider`, implement `complete()`
3. Restart `t01-llm-battle serve` — provider appears in the UI model picker automatically

## Project Layout

```
t01-llm-battle/
├── t01_llm_battle/
│   ├── __init__.py
│   ├── cli.py                      # Typer app — `t01-llm-battle serve`
│   ├── server.py                   # FastAPI app factory + lifespan
│   ├── db/
│   │   ├── schema.py               # CREATE TABLE statements
│   │   └── queries.py              # aiosqlite helpers
│   ├── providers/
│   │   ├── base.py                 # BaseProvider ABC + ModelInfo + CompletionRequest/Result
│   │   ├── registry.py             # Loads built-ins + scans ~/.t01-llm-battle/providers/
│   │   ├── openai.py               # ~80 lines each
│   │   ├── anthropic.py
│   │   ├── google.py
│   │   ├── groq.py
│   │   ├── openrouter.py
│   │   └── ollama.py
│   ├── judge/
│   │   └── scorer.py               # Call judge model, parse score+reasoning, generate markdown report
│   ├── routers/
│   │   ├── battles.py
│   │   ├── runs.py
│   │   └── providers.py
│   └── static/
│       ├── index.html              # Alpine.js SPA shell
│       ├── alpine.min.js           # 15 KB — no CDN dependency
│       ├── marked.min.js           # 50 KB — markdown → HTML
│       ├── easymde.min.js          # 200 KB — markdown editor
│       ├── easymde.min.css
│       └── app.css
├── prd/
├── tests/
├── pyproject.toml
└── README.md
```

## Dependencies

```toml
[project]
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "httpx>=0.27",
    "aiosqlite>=0.20",
    "pydantic-ai>=0.0.36",
]
```

No `rich`, no `pydantic-settings` — intentionally minimal. `pydantic-ai` is the single LLM SDK dependency; tool providers use plain `httpx`.

