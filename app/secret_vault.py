from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

class SecretVaultError(RuntimeError):
    pass

def _fernet() -> Fernet:
    key = os.getenv("GMAI_SECRET_KEY")
    if not key:
        raise SecretVaultError("GMAI_SECRET_KEY is not configured")
    try:
        return Fernet(key.encode())
    except Exception as exc:
        raise SecretVaultError("GMAI_SECRET_KEY is invalid") from exc

@dataclass(frozen=True)
class BrokerCredential:
    account_id: str
    broker: str
    api_key: str
    api_secret: str | None = None
    session_cookie: str | None = None

class SecretVault:
    """Encrypted-at-rest broker credential boundary. Raw secrets are never logged."""

    def encrypt(self, value: str) -> str:
        if not value:
            raise ValueError("secret cannot be empty")
        return _fernet().encrypt(value.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return _fernet().decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise SecretVaultError("secret decryption failed") from exc

    def fingerprint(self, value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()[:12]

def generate_secret_key() -> str:
    return Fernet.generate_key().decode()
