"""
Provider management API.

GET    /providers/pricing        — pricing cache info
POST   /providers/pricing/refresh — fetch latest LLM pricing from LiteLLM
PATCH  /providers/{name}        — toggle enabled/disabled
PUT    /providers/{name}/config — update server_url or other config
DELETE /providers/{name}        — uninstall non-system provider (403 for system)
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import get_db
from ..providers.registry import list_providers, get_provider

_CACHE_DIR = Path.home() / ".t01-llm-battle"
_CACHE_FILE = _CACHE_DIR / "llm_pricing.json"
_LITELLM_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
_PROVIDER_MAP = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google",
    "groq": "groq",
    "openrouter": "openrouter",
}

router = APIRouter(prefix="/providers", tags=["providers"])

# Built-in (system) providers — cannot be uninstalled
_SYSTEM_PROVIDERS = {
    "openai", "anthropic", "google", "groq",
    "openrouter", "ollama", "llm-studio", "serper", "tavily", "firecrawl",
}

# Providers that support a configurable server_url
_SERVER_URL_PROVIDERS = {"ollama", "llm-studio"}


class ProviderPatch(BaseModel):
    enabled: bool


class ProviderConfigUpdate(BaseModel):
    server_url: str | None = None


async def _get_provider_config(db, name: str) -> dict:
    cur = await db.execute(
        "SELECT enabled, server_url FROM provider_config WHERE provider = ?", (name,)
    )
    row = await cur.fetchone()
    if row:
        return {"enabled": bool(row["enabled"]), "server_url": row["server_url"]}
    return {"enabled": True, "server_url": None}


@router.patch("/{name}")
async def toggle_provider(name: str, body: ProviderPatch):
    """Enable or disable a provider."""
    if name not in list_providers():
        raise HTTPException(status_code=404, detail=f"Unknown provider: {name}")

    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            """INSERT INTO provider_config (provider, enabled, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(provider) DO UPDATE SET enabled = excluded.enabled, updated_at = excluded.updated_at""",
            (name, int(body.enabled), now),
        )
        await db.commit()
    return {"provider": name, "enabled": body.enabled}


@router.put("/{name}/config")
async def update_provider_config(name: str, body: ProviderConfigUpdate):
    """Update provider-specific config (e.g. server_url for Ollama)."""
    if name not in list_providers():
        raise HTTPException(status_code=404, detail=f"Unknown provider: {name}")

    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        existing = await _get_provider_config(db, name)
        server_url = body.server_url if body.server_url is not None else existing["server_url"]
        await db.execute(
            """INSERT INTO provider_config (provider, enabled, server_url, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(provider) DO UPDATE SET server_url = excluded.server_url, updated_at = excluded.updated_at""",
            (name, int(existing["enabled"]), server_url, now),
        )
        await db.commit()
    return {"provider": name, "server_url": server_url}


@router.get("/pricing")
async def get_pricing_cache():
    """Return pricing cache info: {models, updated_at, age_days} or null if no cache."""
    if not _CACHE_FILE.exists():
        return None
    try:
        mtime = _CACHE_FILE.stat().st_mtime
        updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        age_days = (datetime.now(timezone.utc).timestamp() - mtime) / 86400
        data = json.loads(_CACHE_FILE.read_text())
        return {"models": len(data), "updated_at": updated_at, "age_days": round(age_days, 1)}
    except Exception:
        return None


@router.post("/pricing/refresh")
async def refresh_pricing():
    """Fetch latest LLM pricing from LiteLLM, normalize, and save to cache."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(_LITELLM_URL)
            resp.raise_for_status()
            raw = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch LiteLLM pricing: {e}")

    normalized: dict = {}
    for key, val in raw.items():
        if not isinstance(val, dict):
            continue
        litellm_provider = val.get("litellm_provider", "")
        our_provider = _PROVIDER_MAP.get(litellm_provider)
        if not our_provider:
            continue
        # Strip provider prefix from key
        slug = key.split("/", 1)[-1] if "/" in key else key
        inp = val.get("input_cost_per_token", 0) * 1_000_000
        out = val.get("output_cost_per_token", 0) * 1_000_000
        # Prefer bare key (no slash) over stripped key to avoid collisions
        entry_key = f"{our_provider}/{slug}"
        if entry_key not in normalized:
            normalized[entry_key] = {"input_per_million": inp, "output_per_million": out}

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(normalized, indent=2))

    updated_at = datetime.now(timezone.utc).isoformat()
    return {"models_updated": len(normalized), "updated_at": updated_at}


@router.delete("/{name}", status_code=204, response_model=None)
async def uninstall_provider(name: str):
    """Uninstall a non-system provider. Returns 403 for system providers."""
    if name in _SYSTEM_PROVIDERS:
        raise HTTPException(status_code=403, detail=f"Cannot uninstall system provider: {name}")
    if name not in list_providers():
        raise HTTPException(status_code=404, detail=f"Unknown provider: {name}")
    # For user-installed providers, just mark as disabled (no registry mutation at runtime)
    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            """INSERT INTO provider_config (provider, enabled, updated_at)
               VALUES (?, 0, ?)
               ON CONFLICT(provider) DO UPDATE SET enabled = 0, updated_at = excluded.updated_at""",
            (name, now),
        )
        await db.commit()
