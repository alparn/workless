"""Tests for the crypto service (AES-256-GCM key encryption)."""

import pytest

from app.services.crypto import decrypt_api_key, encrypt_api_key, mask_key


class TestEncryptDecrypt:
    def test_roundtrip(self):
        key = "sk-ant-api03-some-very-long-test-key-1234567890abcdef"
        encrypted = encrypt_api_key(key)
        assert isinstance(encrypted, bytes)
        assert len(encrypted) > 12
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == key

    def test_different_ciphertexts_per_call(self):
        """Each encryption uses a random nonce, so ciphertexts differ."""
        key = "test-key-abc"
        enc1 = encrypt_api_key(key)
        enc2 = encrypt_api_key(key)
        assert enc1 != enc2
        assert decrypt_api_key(enc1) == decrypt_api_key(enc2) == key

    def test_empty_key(self):
        encrypted = encrypt_api_key("")
        assert decrypt_api_key(encrypted) == ""

    def test_unicode_key(self):
        key = "schlüssel-mit-ümlauten-🔑"
        encrypted = encrypt_api_key(key)
        assert decrypt_api_key(encrypted) == key

    def test_long_key(self):
        key = "x" * 10_000
        encrypted = encrypt_api_key(key)
        assert decrypt_api_key(encrypted) == key

    def test_tampered_blob_raises(self):
        encrypted = encrypt_api_key("secret-key")
        tampered = encrypted[:-1] + bytes([encrypted[-1] ^ 0xFF])
        with pytest.raises(Exception):
            decrypt_api_key(tampered)

    def test_truncated_blob_raises(self):
        encrypted = encrypt_api_key("secret-key")
        with pytest.raises(Exception):
            decrypt_api_key(encrypted[:10])


class TestMaskKey:
    def test_long_key(self):
        result = mask_key("sk-ant-api03-very-long-key-suffix")
        assert result.startswith("sk-ant")
        assert result.endswith("ffix")
        assert "****" in result

    def test_short_key(self):
        assert mask_key("short") == "****"
        assert mask_key("12345678") == "****"

    def test_exactly_9_chars(self):
        result = mask_key("123456789")
        assert result.startswith("123456")
        assert result.endswith("6789")

    def test_typical_anthropic_key(self):
        key = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"
        result = mask_key(key)
        assert "sk-ant" in result
        assert "7890" in result
        assert len(key) > len(result)
