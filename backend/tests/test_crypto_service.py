import pytest
from cryptography.fernet import Fernet

from app.config.settings import settings
from app.services import crypto_service


def test_encrypt_decrypt_roundtrip(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    ciphertext = crypto_service.encrypt("a-secret-token")
    assert ciphertext != "a-secret-token"
    assert crypto_service.decrypt(ciphertext) == "a-secret-token"


def test_encrypt_without_key_raises_configuration_error(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_TOKEN_ENCRYPTION_KEY", None)
    with pytest.raises(crypto_service.ConfigurationError):
        crypto_service.encrypt("x")


def test_encrypt_with_malformed_key_raises_configuration_error(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_TOKEN_ENCRYPTION_KEY", "not-a-valid-fernet-key")
    with pytest.raises(crypto_service.ConfigurationError):
        crypto_service.encrypt("x")


def test_decrypt_with_wrong_key_raises_configuration_error(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    ciphertext = crypto_service.encrypt("a-secret-token")

    monkeypatch.setattr(settings, "EMAIL_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with pytest.raises(crypto_service.ConfigurationError):
        crypto_service.decrypt(ciphertext)
