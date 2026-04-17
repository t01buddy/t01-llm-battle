# Non-Functional Requirements

**Status**: TBD

## Performance

| Requirement | Target |
|-------------|--------|
| `pipx install` to first result | < 2 minutes |
| Cold start to UI ready | < 3 seconds |
| Install size (wheel + deps) | < 15 MB |
| SQLite query latency (battles list) | < 100 ms |

## Privacy & Security

- API keys never logged, never sent to any t01buddy endpoint
- Keys stored in SQLite on local machine only (not synced)
- UI masks key values after entry
- `.env` documented as gitignore'd in README
- No telemetry, no analytics, no cloud calls from the Python backend
- Exception: Ollama calls are proxied through the backend (CORS) — no keys involved

## Packaging

- Distributed via PyPI as a wheel; installed with `pipx`
- Single command: `pipx install t01-llm-battle` → `t01-llm-battle serve`
- No Docker required for standard use; optional Dockerfile for power users
- Cross-platform: macOS, Linux, Windows (WSL acceptable for v0.1)
- Python 3.11+ required (documented in README)

## Reliability

- FastAPI server handles concurrent runs without blocking the UI
- SQLite WAL mode for safe concurrent reads during active runs
- Graceful error surface: provider errors shown per-result, not as full crashes
- Browser refresh recovers live run state via polling endpoint

## Maintainability

- Provider adapters are isolated (~80-line files); adding a new provider requires one new file
- Model catalog is a versioned JSON/Python dict; community PRs welcome
- No official SDK dependencies — `httpx` only; adapters won't break on SDK upgrades
