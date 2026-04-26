import asyncio
import os
import time
from collections import defaultdict, deque

# Default RPM limits per provider (0 = unlimited)
DEFAULT_RPM: dict[str, int] = {
    "openai": 60,
    "anthropic": 50,
    "google": 60,
    "groq": 30,
    "openrouter": 20,
    "ollama": 0,  # 0 = unlimited
    "lmstudio": 0,  # local, unlimited
    "serper": 10,   # free tier: ~600 req/month ≈ 10 RPM burst budget
    "tavily": 10,   # free tier: ~1000 req/month ≈ 10 RPM burst budget
    "firecrawl": 20,  # free tier: ~500 req/month ≈ 20 RPM burst budget
}

# Env var names for per-provider overrides
_ENV_VARS: dict[str, str] = {
    "openai": "T01_RPM_OPENAI",
    "anthropic": "T01_RPM_ANTHROPIC",
    "google": "T01_RPM_GOOGLE",
    "groq": "T01_RPM_GROQ",
    "openrouter": "T01_RPM_OPENROUTER",
    "ollama": "T01_RPM_OLLAMA",
    "lmstudio": "T01_RPM_LMSTUDIO",
    "serper": "T01_RPM_SERPER",
    "tavily": "T01_RPM_TAVILY",
    "firecrawl": "T01_RPM_FIRECRAWL",
}


def _load_limits() -> dict[str, int]:
    """Build effective RPM limits from defaults + env var overrides."""
    limits = dict(DEFAULT_RPM)
    for provider, env_var in _ENV_VARS.items():
        value = os.environ.get(env_var)
        if value is not None:
            try:
                limits[provider] = int(value)
            except ValueError:
                pass  # ignore malformed env var
    return limits


class RateLimiter:
    """Per-provider sliding-window rate limiter.

    Uses asyncio.sleep for backoff — never blocks the event loop.
    Limits are loaded from DEFAULT_RPM and can be overridden via env vars
    (T01_RPM_OPENAI, T01_RPM_ANTHROPIC, T01_RPM_GOOGLE, T01_RPM_GROQ,
    T01_RPM_OPENROUTER, T01_RPM_OLLAMA, T01_RPM_LMSTUDIO,
    T01_RPM_SERPER, T01_RPM_TAVILY, T01_RPM_FIRECRAWL).
    """

    def __init__(self, limits: dict[str, int] | None = None):
        if limits is not None:
            self._limits = limits
        else:
            self._limits = _load_limits()
        self._windows: dict[str, deque] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def acquire(self, provider: str) -> None:
        """Wait until a request slot is available for the provider."""
        rpm = self._limits.get(provider, 60)
        if rpm == 0:
            return  # unlimited

        async with self._lock:
            now = time.monotonic()
            window = self._windows[provider]

            # Remove timestamps older than 60 seconds
            while window and window[0] <= now - 60:
                window.popleft()

            if len(window) >= rpm:
                # Must wait until oldest request leaves the window
                sleep_for = 60 - (now - window[0]) + 0.01
                await asyncio.sleep(sleep_for)
                # Re-prune after sleep
                now = time.monotonic()
                while window and window[0] <= now - 60:
                    window.popleft()

            window.append(time.monotonic())


# Module-level singleton — shared across the execution engine
_limiter = RateLimiter()


def get_limiter() -> RateLimiter:
    """Return the shared singleton RateLimiter."""
    return _limiter


async def acquire(provider: str) -> None:
    """Acquire a rate-limit slot for the given provider (singleton)."""
    await _limiter.acquire(provider)
