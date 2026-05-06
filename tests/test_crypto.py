"""Unit tests for t01_llm_battle.crypto — encrypt/decrypt/is_encrypted."""
from __future__ import annotations

import stat
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.fernet import InvalidToken

import t01_llm_battle.crypto as crypto_module


@pytest.fixture(autouse=True)
def isolated_keyfile(tmp_path, monkeypatch):
    """Point _KEYFILE to a tmp dir and reset the cached _fernet between tests."""
    keyfile = tmp_path / ".keyfile"
    monkeypatch.setattr(crypto_module, "_KEYFILE", keyfile)
    monkeypatch.setattr(crypto_module, "_fernet", None)
    yield keyfile
    # reset after test
    monkeypatch.setattr(crypto_module, "_fernet", None)


# ---------------------------------------------------------------------------
# encrypt_key / decrypt_key round-trip
# ---------------------------------------------------------------------------

def test_round_trip():
    plaintext = "sk-test-1234567890"
    token = crypto_module.encrypt_key(plaintext)
    assert crypto_module.decrypt_key(token) == plaintext


def test_encrypt_produces_different_ciphertext_each_time():
    """Fernet uses random IV — same plaintext → different ciphertext."""
    token1 = crypto_module.encrypt_key("secret")
    token2 = crypto_module.encrypt_key("secret")
    assert token1 != token2


# ---------------------------------------------------------------------------
# is_encrypted
# ---------------------------------------------------------------------------

def test_is_encrypted_true_for_fernet_token():
    token = crypto_module.encrypt_key("anything")
    assert crypto_module.is_encrypted(token) is True


def test_is_encrypted_false_for_plaintext():
    assert crypto_module.is_encrypted("sk-plaintext-key") is False


def test_is_encrypted_false_for_empty_string():
    assert crypto_module.is_encrypted("") is False


def test_is_encrypted_false_for_arbitrary_string():
    assert crypto_module.is_encrypted("not-a-fernet-token") is False


# ---------------------------------------------------------------------------
# Keyfile bootstrap
# ---------------------------------------------------------------------------

def test_keyfile_created_on_first_call(isolated_keyfile):
    assert not isolated_keyfile.exists()
    crypto_module.encrypt_key("bootstrap")
    assert isolated_keyfile.exists()


def test_keyfile_mode_0600(isolated_keyfile):
    crypto_module.encrypt_key("bootstrap")
    mode = stat.S_IMODE(isolated_keyfile.stat().st_mode)
    assert mode == 0o600


def test_keyfile_reused_across_calls(isolated_keyfile):
    """Subsequent calls must use the same key (decrypt what encrypt produced)."""
    token = crypto_module.encrypt_key("reuse-me")
    # Force fernet cache to None to simulate a second process reading the keyfile
    crypto_module._fernet = None
    assert crypto_module.decrypt_key(token) == "reuse-me"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_decrypt_raises_on_tampered_ciphertext():
    token = crypto_module.encrypt_key("legit")
    tampered = token[:-4] + "XXXX"
    with pytest.raises(InvalidToken):
        crypto_module.decrypt_key(tampered)


def test_decrypt_raises_on_plaintext_input():
    with pytest.raises(Exception):
        crypto_module.decrypt_key("sk-not-a-token")
