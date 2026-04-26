"""Tests for OllamaProvider.models() using DB-configured server_url (FR-8)."""
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from t01_llm_battle.providers.ollama import OllamaProvider


def test_models_uses_db_server_url(tmp_path):
    """models() must query the DB-configured server_url, not the hardcoded default."""
    db_path = tmp_path / "test.db"
    con = sqlite3.connect(str(db_path))
    con.execute(
        "CREATE TABLE provider_config (provider TEXT PRIMARY KEY, server_url TEXT)"
    )
    con.execute(
        "INSERT INTO provider_config (provider, server_url) VALUES ('ollama', 'http://custom-ollama:12345')"
    )
    con.commit()
    con.close()

    provider = OllamaProvider()

    with patch("t01_llm_battle.providers.ollama.DB_PATH", db_path):
        with patch("t01_llm_battle.providers.ollama.httpx.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"models": [{"name": "llama3"}, {"name": "mistral"}]}
            mock_get.return_value = mock_resp

            result = provider.models()

    # Verify custom URL was used
    mock_get.assert_called_once_with("http://custom-ollama:12345/api/tags", timeout=5.0)
    assert result == ["llama3", "mistral"]


def test_models_falls_back_to_default_when_no_db_config(tmp_path):
    """models() falls back to default URL when provider_config has no server_url."""
    db_path = tmp_path / "test.db"
    con = sqlite3.connect(str(db_path))
    con.execute(
        "CREATE TABLE provider_config (provider TEXT PRIMARY KEY, server_url TEXT)"
    )
    con.commit()
    con.close()

    provider = OllamaProvider(base_url="http://localhost:11434")

    with patch("t01_llm_battle.providers.ollama.DB_PATH", db_path):
        with patch("t01_llm_battle.providers.ollama.httpx.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"models": []}
            mock_get.return_value = mock_resp

            result = provider.models()

    mock_get.assert_called_once_with("http://localhost:11434/api/tags", timeout=5.0)
    assert result == []


def test_models_returns_empty_on_connection_error(tmp_path):
    """models() returns [] if Ollama is not running."""
    db_path = tmp_path / "empty.db"
    provider = OllamaProvider()

    with patch("t01_llm_battle.providers.ollama.DB_PATH", db_path):
        with patch("t01_llm_battle.providers.ollama.httpx.get", side_effect=Exception("refused")):
            result = provider.models()

    assert result == []
