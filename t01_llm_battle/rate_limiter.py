import asyncio
import time
from collections import defaultdict, deque

# Default RPM limits per provider
DEFAULT_RPM = {
    "openai": 60,
    "anthropic": 60,
    "google": 60,
    "groq": 30,
    "openrouter": 20,
    "ollama": 0,  # 0 = unlimited
}


class RateLimiter:
    """Per-provider sliding-window rate limiter."""

    def __init__(self, limits: dict[str, int] | None = None):
        self._limits = {**DEFAULT_RPM, **(limits or {})}
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


# Module-level singleton
_limiter = RateLimiter()


async def acquire(provider: str) -> None:
    await _limiter.acquire(provider)
