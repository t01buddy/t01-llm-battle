"""Centralized pricing module — loads, serves, and refreshes LLM and tool pricing."""

from __future__ import annotations

import json
import time
from importlib.resources import files
from pathlib import Path
from typing import Any

_CACHE_DIR = Path.home() / ".t01-llm-battle"
_LLM_CACHE = _CACHE_DIR / "llm_pricing.json"

_LITELLM_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main"
    "/model_prices_and_context_window.json"
)

_PROVIDER_MAP = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google",
    "gemini": "google",
    "groq": "groq",
    "openrouter": "openrouter",
}

_SUPPORTED_PROVIDERS = set(_PROVIDER_MAP.values())


def _load_bundled(name: str) -> dict[str, Any]:
    pkg = files("t01_llm_battle")
    return json.loads((pkg / name).read_text(encoding="utf-8"))


def load_llm_pricing() -> dict[str, Any]:
    """Load bundled llm_pricing.json, overlaid with user cache if present."""
    data: dict[str, Any] = _load_bundled("llm_pricing.json")
    if _LLM_CACHE.exists():
        try:
            cached = json.loads(_LLM_CACHE.read_text(encoding="utf-8"))
            for provider, models in cached.items():
                if provider not in data:
                    data[provider] = {}
                data[provider].update(models)
        except (json.JSONDecodeError, OSError):
            pass
    return data


def load_tool_pricing() -> dict[str, Any]:
    """Load bundled tool_pricing.json."""
    return _load_bundled("tool_pricing.json")


def get_llm_models(provider: str) -> list[str]:
    """Return model slugs for a provider."""
    return list(load_llm_pricing().get(provider, {}).keys())


def get_llm_cost(
    provider: str, model: str, input_tokens: int, output_tokens: int
) -> float | None:
    """Calculate cost in USD. Returns None for unknown provider/model."""
    pricing = load_llm_pricing()
    entry = pricing.get(provider, {}).get(model)
    if entry is None:
        return None
    return (
        input_tokens * entry["input_per_million"]
        + output_tokens * entry["output_per_million"]
    ) / 1_000_000


def get_tool_functions(provider: str) -> list[str]:
    """Return function list for a tool provider."""
    tool = load_tool_pricing().get(provider, {})
    return tool.get("functions", [])


def get_tool_cost(provider: str) -> float:
    """Return cost per call in USD."""
    tool = load_tool_pricing().get(provider, {})
    return tool.get("credits_per_call", 0.0) * tool.get("usd_per_credit", 0.0)


def get_cache_info() -> dict[str, Any]:
    """Return cache age in seconds and model count."""
    if not _LLM_CACHE.exists():
        return {"age_seconds": None, "model_count": 0}
    age = time.time() - _LLM_CACHE.stat().st_mtime
    try:
        cached = json.loads(_LLM_CACHE.read_text(encoding="utf-8"))
        count = sum(len(v) for v in cached.values())
    except (json.JSONDecodeError, OSError):
        count = 0
    return {"age_seconds": int(age), "model_count": count}


def refresh_llm_pricing() -> dict[str, int]:
    """Fetch LiteLLM pricing JSON, normalize, write cache. Returns per-provider counts."""
    import urllib.request

    with urllib.request.urlopen(_LITELLM_URL, timeout=15) as resp:
        raw: dict[str, Any] = json.loads(resp.read().decode("utf-8"))

    result: dict[str, dict[str, Any]] = {}
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        litellm_provider = entry.get("litellm_provider", "")
        our_provider = _PROVIDER_MAP.get(litellm_provider)
        if our_provider not in _SUPPORTED_PROVIDERS:
            continue
        input_cost = entry.get("input_cost_per_token")
        output_cost = entry.get("output_cost_per_token")
        if input_cost is None or output_cost is None:
            continue

        # Strip provider prefix: "groq/llama-3.3-70b" -> "llama-3.3-70b"
        slug = key.split("/", 1)[-1] if "/" in key else key

        if our_provider not in result:
            result[our_provider] = {}
        # Prefer bare key over stripped key on collision
        if slug not in result[our_provider]:
            result[our_provider][slug] = {
                "input_per_million": round(input_cost * 1_000_000, 6),
                "output_per_million": round(output_cost * 1_000_000, 6),
            }

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _LLM_CACHE.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return {p: len(m) for p, m in result.items()}
