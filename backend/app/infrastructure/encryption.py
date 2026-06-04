"""
Encryption utilities using Fernet (symmetric encryption).

Used for storing Salesforce access tokens, refresh tokens, and private keys.
"""

from cryptography.fernet import Fernet

from app.core.config import get_settings

_settings = get_settings()

# In production you should load this from a secure secret manager
_fernet = Fernet(_settings.fernet_key.encode())


def encrypt(data: str) -> str:
    return _fernet.encrypt(data.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet.decrypt(token.encode()).decode()
