"""
API key management.
Env-wins logic: if PROVIDER_API_KEY env var is set, it overrides any DB value.
GET /keys — list all providers with key status (set/unset, source: env/db)
GET /keys/{provider} — get key for provider (masked)
PUT /keys/{provider} — store key in DB (also accepts display_name, base_url)
DELETE /keys/{provider} — remove key from DB
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..crypto import decrypt_key, encrypt_key, is_encrypted
from ..db import get_db

router = APIRouter(prefix="/keys", tags=["keys"])

# Map provider name → env var name (None = no API key needed, e.g. local providers)
_ENV_VARS: dict[str, str | None] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "serper": "SERPER_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "firecrawl": "FIRECRAWL_API_KEY",
    "ollama": None,      # local — no API key
    "llm-studio": None,  # local — no API key
}

# Default base URLs for local providers
_DEFAULT_BASE_URLS: dict[str, str] = {
    "ollama": "http://localhost:11434",
    "llm-studio": "http://localhost:1234",
}


class KeyStatus(BaseModel):
    provider: str
    set: bool
    source: str  # "env", "db", or "none"
    masked_key: str | None = None
    display_name: str | None = None
    base_url: str | None = None


class KeyUpdate(BaseModel):
    key: str | None = None
    display_name: str | None = None
    base_url: str | None = None


def _mask_key(key: str) -> str:
    """Return masked version: first 3 + '…' + last 3 for keys ≥ 8 chars, else '***'."""
    if len(key) >= 8:
        return key[:3] + "…" + key[-3:]
    return "***"


async def _resolve_key(provider: str) -> tuple[bool, str, str | None]:
    """
    Resolve a key using env-wins logic.
    Returns (is_set, source, raw_key_or_None).
    """
    env_var = _ENV_VARS.get(provider)

    # 1. Check env var (only for providers that have one)
    if env_var:
        env_val = os.environ.get(env_var)
        if env_val:
            return True, "env", env_val

    # 2. Check DB
    async with get_db() as db:
        row = await db.execute(
            "SELECT key_value FROM api_key WHERE provider = ?", (provider,)
        )
        result = await row.fetchone()
        if result and result["key_value"]:
            raw = result["key_value"]
            plaintext = decrypt_key(raw) if is_encrypted(raw) else raw
            return True, "db", plaintext

    return False, "none", None


async def _resolve_provider_config(provider: str) -> tuple[str | None, str | None]:
    """Return (display_name, base_url) from provider_config table."""
    async with get_db() as db:
        row = await db.execute(
            "SELECT display_name, server_url FROM provider_config WHERE provider = ?",
            (provider,),
        )
        result = await row.fetchone()
        if result:
            return result["display_name"], result["server_url"]
    return None, None


@router.get("", response_model=list[KeyStatus])
async def list_keys():
    """List all provider key statuses including display_name and base_url."""
    statuses = []
    for provider in _ENV_VARS:
        is_set, source, raw_key = await _resolve_key(provider)
        display_name, base_url = await _resolve_provider_config(provider)
        statuses.append(
            KeyStatus(
                provider=provider,
                set=is_set,
                source=source,
                masked_key=_mask_key(raw_key) if raw_key else None,
                display_name=display_name,
                base_url=base_url or _DEFAULT_BASE_URLS.get(provider),
            )
        )
    return statuses


@router.get("/{provider}", response_model=KeyStatus)
async def get_key(provider: str):
    """Get key status for a provider."""
    if provider not in _ENV_VARS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    is_set, source, raw_key = await _resolve_key(provider)
    display_name, base_url = await _resolve_provider_config(provider)
    return KeyStatus(
        provider=provider,
        set=is_set,
        source=source,
        masked_key=_mask_key(raw_key) if raw_key else None,
        display_name=display_name,
        base_url=base_url or _DEFAULT_BASE_URLS.get(provider),
    )


@router.put("/{provider}")
async def set_key(provider: str, body: KeyUpdate):
    """Store key, display_name, and/or base_url in DB."""
    if provider not in _ENV_VARS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    now = datetime.now(timezone.utc).isoformat()

    async with get_db() as db:
        # Update API key if provided
        if body.key is not None:
            if not body.key.strip():
                raise HTTPException(status_code=422, detail="Key must not be empty")
            encrypted = encrypt_key(body.key.strip())
            await db.execute(
                """
                INSERT INTO api_key (provider, key_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET key_value = excluded.key_value, updated_at = excluded.updated_at
                """,
                (provider, encrypted, now),
            )

        # Update display_name and/or base_url if provided
        if body.display_name is not None or body.base_url is not None:
            await db.execute(
                """
                INSERT INTO provider_config (provider, display_name, server_url, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    display_name = COALESCE(excluded.display_name, display_name),
                    server_url = COALESCE(excluded.server_url, server_url),
                    updated_at = excluded.updated_at
                """,
                (provider, body.display_name, body.base_url, now),
            )

        await db.commit()

    return {"provider": provider, "status": "saved"}


@router.delete("/{provider}")
async def delete_key(provider: str):
    """Remove a key from the DB."""
    if provider not in _ENV_VARS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    env_var = _ENV_VARS[provider]
    if env_var is None:
        raise HTTPException(status_code=422, detail=f"Provider {provider!r} uses no API key")

    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM api_key WHERE provider = ?", (provider,)
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404, detail=f"No DB key found for provider: {provider}"
            )

    return {"provider": provider, "status": "deleted"}
