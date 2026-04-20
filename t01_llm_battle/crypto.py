"""Fernet-based encryption for API keys stored in SQLite.

Key file: ~/.t01-llm-battle/.keyfile (machine-local, never committed).
If the keyfile doesn't exist it is generated on first call.
"""
from __future__ import annotations

from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_KEYFILE: Path = Path.home() / ".t01-llm-battle" / ".keyfile"
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    _KEYFILE.parent.mkdir(parents=True, exist_ok=True)
    if _KEYFILE.exists():
        key = _KEYFILE.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        _KEYFILE.write_bytes(key)
        _KEYFILE.chmod(0o600)

    _fernet = Fernet(key)
    return _fernet


def encrypt_key(plaintext: str) -> str:
    """Encrypt a plaintext API key; return Fernet token as str."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_key(token: str) -> str:
    """Decrypt a Fernet token; return plaintext. Raises InvalidToken if corrupted."""
    return _get_fernet().decrypt(token.encode()).decode()


def is_encrypted(value: str) -> bool:
    """Return True if value looks like a Fernet token (starts with 'gAAA')."""
    return value.startswith("gAAA")
