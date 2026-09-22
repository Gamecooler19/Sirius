"""Symmetric (Fernet) encryption for secrets stored at rest.

Two independent keys, both required at startup (`app.core.config`):
- `SESSION_ENCRYPTION_KEY` encrypts session payloads stored in Valkey.
- `TOTP_ENCRYPTION_KEY` encrypts `user.totp_secret_encrypted` in Postgres.

Separate keys, not one shared key, so rotating one (a session-store key, say,
after a Valkey-adjacent incident) never requires touching the other, and a
leak of one key does not automatically also compromise the other category of
secret.
"""

from cryptography.fernet import Fernet

from app.core.config import get_settings

settings = get_settings()

_session_fernet = Fernet(settings.SESSION_ENCRYPTION_KEY.encode())
_totp_fernet = Fernet(settings.TOTP_ENCRYPTION_KEY.encode())


def encrypt_session_payload(plaintext: str) -> str:
    return _session_fernet.encrypt(plaintext.encode()).decode()


def decrypt_session_payload(ciphertext: str) -> str:
    return _session_fernet.decrypt(ciphertext.encode()).decode()


def encrypt_totp_secret(plaintext: str) -> str:
    return _totp_fernet.encrypt(plaintext.encode()).decode()


def decrypt_totp_secret(ciphertext: str) -> str:
    return _totp_fernet.decrypt(ciphertext.encode()).decode()
