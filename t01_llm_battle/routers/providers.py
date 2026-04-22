"""
Provider management API.

PATCH  /providers/{name}        — toggle enabled/disabled
PUT    /providers/{name}/config — update server_url or other config
DELETE /providers/{name}        — uninstall non-system provider (403 for system)
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import get_db
from ..providers.registry import list_providers, get_provider

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
