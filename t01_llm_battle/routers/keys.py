"""
API key management.
Env-wins logic: if PROVIDER_API_KEY env var is set, it overrides any DB value.
GET /keys — list all providers with key status (set/unset, source: env/db)
GET /keys/{provider} — get key for provider (masked)
PUT /keys/{provider} — store key in DB
DELETE /keys/{provider} — remove key from DB
"""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import get_db

router = APIRouter(prefix="/keys", tags=["keys"])

# Map provider name → env var name
_ENV_VARS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


class KeyStatus(BaseModel):
    provider: str
    set: bool
    source: str  # "env", "db", or "none"
    masked_key: str | None = None


class KeyUpdate(BaseModel):
    key: str


def _mask_key(key: str) -> str:
    """Return masked version: first 4 chars + '****' for keys longer than 8 chars."""
    if len(key) > 8:
        return key[:4] + "****"
    return "****"


async def _resolve_key(provider: str) -> tuple[bool, str, str | None]:
    """
    Resolve a key using env-wins logic.
    Returns (is_set, source, raw_key_or_None).
    """
    env_var = _ENV_VARS.get(provider)

    # 1. Check env var
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
            return True, "db", result["key_value"]

    return False, "none", None


@router.get("", response_model=list[KeyStatus])
async def list_keys():
    """List all provider key statuses."""
    statuses = []
    for provider in _ENV_VARS:
        is_set, source, raw_key = await _resolve_key(provider)
        statuses.append(
            KeyStatus(
                provider=provider,
                set=is_set,
                source=source,
                masked_key=_mask_key(raw_key) if raw_key else None,
            )
        )
    return statuses


@router.get("/{provider}", response_model=KeyStatus)
async def get_key(provider: str):
    """Get key status for a provider."""
    if provider not in _ENV_VARS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    is_set, source, raw_key = await _resolve_key(provider)
    return KeyStatus(
        provider=provider,
        set=is_set,
        source=source,
        masked_key=_mask_key(raw_key) if raw_key else None,
    )


@router.put("/{provider}")
async def set_key(provider: str, body: KeyUpdate):
    """Store a key in the DB (env var takes precedence at runtime)."""
    if provider not in _ENV_VARS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    if not body.key or not body.key.strip():
        raise HTTPException(status_code=422, detail="Key must not be empty")

    now = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO api_key (provider, key_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(provider) DO UPDATE SET key_value = excluded.key_value, updated_at = excluded.updated_at
            """,
            (provider, body.key.strip(), now),
        )
        await db.commit()

    return {"provider": provider, "status": "saved"}


@router.delete("/{provider}")
async def delete_key(provider: str):
    """Remove a key from the DB."""
    if provider not in _ENV_VARS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

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
