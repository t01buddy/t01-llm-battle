"""Tests for t01_llm_battle.pricing module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from t01_llm_battle import pricing as pricing_module
from t01_llm_battle.pricing import (
    get_cache_info,
    get_llm_cost,
    get_llm_models,
    get_tool_cost,
    get_tool_functions,
    load_llm_pricing,
    load_tool_pricing,
    refresh_llm_pricing,
)


def test_load_llm_pricing_returns_dict():
    data = load_llm_pricing()
    assert isinstance(data, dict)
    assert "openai" in data
    assert "anthropic" in data
    assert "google" in data
    assert "groq" in data


def test_load_llm_pricing_model_entries():
    data = load_llm_pricing()
    entry = data["openai"]["gpt-4o"]
    assert "input_per_million" in entry
    assert "output_per_million" in entry
    assert entry["input_per_million"] == pytest.approx(2.50)


def test_load_tool_pricing_returns_dict():
    data = load_tool_pricing()
    assert isinstance(data, dict)
    assert "serper" in data
    assert "tavily" in data
    assert "firecrawl" in data


def test_load_tool_pricing_structure():
    data = load_tool_pricing()
    entry = data["tavily"]
    assert "functions" in entry
    assert "credits_per_call" in entry
    assert "usd_per_credit" in entry


def test_get_llm_models():
    models = get_llm_models("openai")
    assert "gpt-4o" in models
    assert "gpt-4o-mini" in models


def test_get_llm_models_unknown_provider():
    assert get_llm_models("nonexistent") == []


def test_get_llm_cost():
    cost = get_llm_cost("openai", "gpt-4o", 1_000_000, 1_000_000)
    assert cost == pytest.approx(2.50 + 10.00)


def test_get_llm_cost_zero_tokens():
    assert get_llm_cost("openai", "gpt-4o", 0, 0) == 0.0


def test_get_llm_cost_unknown_model():
    assert get_llm_cost("openai", "nonexistent-model", 1000, 1000) is None


def test_get_llm_cost_unknown_provider():
    assert get_llm_cost("unknown", "gpt-4o", 1000, 1000) is None


def test_get_tool_functions():
    funcs = get_tool_functions("serper")
    assert "search" in funcs


def test_get_tool_functions_unknown():
    assert get_tool_functions("unknown") == []


def test_get_tool_cost():
    cost = get_tool_cost("serper")
    assert cost == pytest.approx(0.001)

    cost = get_tool_cost("tavily")
    assert cost == pytest.approx(0.002)


def test_get_tool_cost_unknown():
    assert get_tool_cost("nonexistent") == 0.0


def test_get_cache_info_no_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(pricing_module, "_LLM_CACHE", tmp_path / "no_such_file.json")
    info = get_cache_info()
    assert info["age_seconds"] is None
    assert info["model_count"] == 0


def test_get_cache_info_with_cache(tmp_path, monkeypatch):
    cache_file = tmp_path / "llm_pricing.json"
    cache_file.write_text(
        json.dumps({"openai": {"gpt-4o": {}, "gpt-4o-mini": {}}}), encoding="utf-8"
    )
    monkeypatch.setattr(pricing_module, "_LLM_CACHE", cache_file)
    info = get_cache_info()
    assert info["age_seconds"] is not None
    assert info["model_count"] == 2


def test_cache_overlay_overrides_bundled(tmp_path, monkeypatch):
    cache_file = tmp_path / "llm_pricing.json"
    cache_file.write_text(
        json.dumps({"openai": {"gpt-4o": {"input_per_million": 999.0, "output_per_million": 999.0}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(pricing_module, "_LLM_CACHE", cache_file)
    data = load_llm_pricing()
    assert data["openai"]["gpt-4o"]["input_per_million"] == pytest.approx(999.0)


def test_cache_overlay_corrupt_falls_back(tmp_path, monkeypatch):
    cache_file = tmp_path / "llm_pricing.json"
    cache_file.write_text("not valid json", encoding="utf-8")
    monkeypatch.setattr(pricing_module, "_LLM_CACHE", cache_file)
    # Should not raise; falls back to bundled data
    data = load_llm_pricing()
    assert "openai" in data


def test_refresh_llm_pricing(tmp_path, monkeypatch):
    fake_litellm = {
        "gpt-4o": {
            "litellm_provider": "openai",
            "input_cost_per_token": 0.000002,
            "output_cost_per_token": 0.000006,
        },
        "openai/gpt-4o": {
            "litellm_provider": "openai",
            "input_cost_per_token": 0.000001,
            "output_cost_per_token": 0.000003,
        },
        "groq/llama-3.3-70b-versatile": {
            "litellm_provider": "groq",
            "input_cost_per_token": 0.00000059,
            "output_cost_per_token": 0.00000079,
        },
        "azure/gpt-4": {
            "litellm_provider": "azure",
            "input_cost_per_token": 0.00003,
            "output_cost_per_token": 0.00006,
        },
    }

    import io
    import urllib.request

    class FakeResp:
        def read(self):
            return json.dumps(fake_litellm).encode()
        def __enter__(self): return self
        def __exit__(self, *a): pass

    monkeypatch.setattr(pricing_module, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(pricing_module, "_LLM_CACHE", tmp_path / "llm_pricing.json")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())

    counts = refresh_llm_pricing()
    assert "openai" in counts
    assert "groq" in counts
    # azure should be skipped
    assert "azure" not in counts

    written = json.loads((tmp_path / "llm_pricing.json").read_text())
    # Bare key "gpt-4o" preferred over stripped "openai/gpt-4o"
    assert "gpt-4o" in written["openai"]
    assert written["openai"]["gpt-4o"]["input_per_million"] == pytest.approx(2.0)
    # Groq prefix stripped
    assert "llama-3.3-70b-versatile" in written["groq"]
