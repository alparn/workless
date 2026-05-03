"""Symmetric encryption for API keys stored in the database.

Uses AES-256-GCM via the ``cryptography`` library.  The master key is
read from the ``LLM_KEY_ENCRYPTION_SECRET`` env-var (32-byte hex string).
If the env-var is absent a deterministic fallback is derived from the
DATABASE_URL so that the app still starts in development — but a real
secret MUST be set in production.
"""

import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _derive_master_key() -> bytes:
    env_secret = os.getenv("LLM_KEY_ENCRYPTION_SECRET", "")
    if env_secret:
        return bytes.fromhex(env_secret)
    db_url = os.getenv("DATABASE_URL", "fallback-dev-only")
    return hashlib.sha256(db_url.encode()).digest()


_MASTER_KEY: bytes = _derive_master_key()


def encrypt_api_key(plaintext: str) -> bytes:
    """Return nonce‖ciphertext (12 + len bytes)."""
    nonce = os.urandom(12)
    ct = AESGCM(_MASTER_KEY).encrypt(nonce, plaintext.encode(), None)
    return nonce + ct


def decrypt_api_key(blob: bytes) -> str:
    """Decrypt a blob produced by ``encrypt_api_key``."""
    nonce, ct = blob[:12], blob[12:]
    return AESGCM(_MASTER_KEY).decrypt(nonce, ct, None).decode()


def mask_key(plaintext: str) -> str:
    """Return a UI-safe masked version, e.g. ``sk-ant-...****7x2f``."""
    if len(plaintext) <= 8:
        return "****"
    return f"{plaintext[:6]}...****{plaintext[-4:]}"
