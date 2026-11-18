from cryptography.fernet import Fernet
import pytest
from app.secret_vault import SecretVault, SecretVaultError

def test_secret_round_trip(monkeypatch):
    monkeypatch.setenv("GMAI_SECRET_KEY", Fernet.generate_key().decode())
    vault = SecretVault()
    ciphertext = vault.encrypt("super-secret")
    assert ciphertext != "super-secret"
    assert vault.decrypt(ciphertext) == "super-secret"

def test_missing_key_is_rejected(monkeypatch):
    monkeypatch.delenv("GMAI_SECRET_KEY", raising=False)
    with pytest.raises(SecretVaultError):
        SecretVault().encrypt("secret")
