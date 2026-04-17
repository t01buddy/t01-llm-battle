"""Tests for t01_llm_battle.rate_limiter."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from t01_llm_battle.rate_limiter import (
    DEFAULT_RPM,
    RateLimiter,
    _load_limits,
    acquire,
    get_limiter,
)


# ---------------------------------------------------------------------------
# Default limits
# ---------------------------------------------------------------------------

def test_default_rpm_values():
    assert DEFAULT_RPM["openai"] == 60
    assert DEFAULT_RPM["anthropic"] == 50
    assert DEFAULT_RPM["google"] == 60
    assert DEFAULT_RPM["groq"] == 30
    assert DEFAULT_RPM["openrouter"] == 20
    assert DEFAULT_RPM["ollama"] == 0  # unlimited


# ---------------------------------------------------------------------------
# Env var overrides
# ---------------------------------------------------------------------------

def test_env_var_override_openai(monkeypatch):
    monkeypatch.setenv("T01_RPM_OPENAI", "10")
    limits = _load_limits()
    assert limits["openai"] == 10


def test_env_var_override_anthropic(monkeypatch):
    monkeypatch.setenv("T01_RPM_ANTHROPIC", "5")
    limits = _load_limits()
    assert limits["anthropic"] == 5


def test_env_var_override_all_providers(monkeypatch):
    monkeypatch.setenv("T01_RPM_OPENAI", "1")
    monkeypatch.setenv("T01_RPM_ANTHROPIC", "2")
    monkeypatch.setenv("T01_RPM_GOOGLE", "3")
    monkeypatch.setenv("T01_RPM_GROQ", "4")
    monkeypatch.setenv("T01_RPM_OPENROUTER", "5")
    monkeypatch.setenv("T01_RPM_OLLAMA", "0")
    limits = _load_limits()
    assert limits["openai"] == 1
    assert limits["anthropic"] == 2
    assert limits["google"] == 3
    assert limits["groq"] == 4
    assert limits["openrouter"] == 5
    assert limits["ollama"] == 0


def test_env_var_malformed_is_ignored(monkeypatch):
    monkeypatch.setenv("T01_RPM_OPENAI", "not-a-number")
    limits = _load_limits()
    # Falls back to default
    assert limits["openai"] == DEFAULT_RPM["openai"]


def test_rate_limiter_respects_env_var_at_construction(monkeypatch):
    monkeypatch.setenv("T01_RPM_GROQ", "7")
    limiter = RateLimiter()
    assert limiter._limits["groq"] == 7


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

def test_singleton_is_shared():
    limiter1 = get_limiter()
    limiter2 = get_limiter()
    assert limiter1 is limiter2


# ---------------------------------------------------------------------------
# Unlimited provider (ollama) — acquire returns immediately
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_acquire_unlimited_returns_immediately():
    limiter = RateLimiter(limits={"ollama": 0})
    t0 = time.monotonic()
    for _ in range(100):
        await limiter.acquire("ollama")
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5, "Unlimited provider should not sleep"


# ---------------------------------------------------------------------------
# Within-limit calls — no sleep
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_acquire_within_limit_no_sleep():
    """Calls under the RPM cap should not trigger asyncio.sleep."""
    limiter = RateLimiter(limits={"testprovider": 10})
    sleep_calls = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    with patch("t01_llm_battle.rate_limiter.asyncio.sleep", side_effect=fake_sleep):
        for _ in range(5):
            await limiter.acquire("testprovider")

    assert sleep_calls == [], "Should not sleep when under limit"


# ---------------------------------------------------------------------------
# At-limit calls — asyncio.sleep is used (not blocking)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_acquire_at_limit_uses_asyncio_sleep():
    """When the window is full, asyncio.sleep must be called (not time.sleep)."""
    rpm = 3
    limiter = RateLimiter(limits={"testprovider": rpm})
    sleep_calls = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)
        # Advance the internal window timestamps so re-prune clears them
        window = limiter._windows["testprovider"]
        now = time.monotonic()
        for i in range(len(window)):
            window[i] = now - 61  # expire all

    with patch("t01_llm_battle.rate_limiter.asyncio.sleep", side_effect=fake_sleep):
        for _ in range(rpm + 1):  # one more than the limit
            await limiter.acquire("testprovider")

    assert len(sleep_calls) >= 1, "asyncio.sleep should be called when limit is hit"


# ---------------------------------------------------------------------------
# Module-level acquire() uses singleton
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_module_level_acquire_uses_singleton():
    """The module-level acquire() function must delegate to the singleton."""
    limiter = get_limiter()
    acquire_calls = []

    original_acquire = limiter.acquire

    async def spy_acquire(provider):
        acquire_calls.append(provider)
        # Skip actual sleeping by using an unlimited window
        pass

    with patch.object(limiter, "acquire", side_effect=spy_acquire):
        await acquire("openai")

    assert "openai" in acquire_calls


# ---------------------------------------------------------------------------
# Unknown provider falls back gracefully
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_acquire_unknown_provider_uses_default():
    """Providers not in the limits dict default to 60 RPM (no crash)."""
    limiter = RateLimiter(limits={})  # empty — unknown provider
    # Should not raise
    for _ in range(5):
        await limiter.acquire("unknown-provider")
