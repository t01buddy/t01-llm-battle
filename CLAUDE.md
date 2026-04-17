# t01-llm-battle — Local LLM Battle Arena

OSS Python tool. `pipx install t01-llm-battle && t01-llm-battle serve` → browser opens.

## PRD

@prd/01-prd.md (Vision, scope, architecture principles)
@prd/02-tech-stack.md (Stack, project layout)
@prd/03-functional-requirements.md (FR index)
@prd/04-non-functional-requirements.md (Performance, privacy, packaging)
@prd/05-user-stories.md (Key workflows)
@prd/06-data-models.md (SQLite schema)
@prd/07-roadmap.md (v0.1 scope + future)

## Key rules

- Never commit API keys or `.env`
- No streaming in v0.1 (full responses only)
- No accounts, no cloud, no SaaS — ever
- Provider adapters are thin httpx clients (~80 lines each), no official SDKs
- SQLite only — no Celery, Redis, or worker pool
- Python module name: `t01_llm_battle`
- User plugin dir: `~/.t01-llm-battle/providers/`
