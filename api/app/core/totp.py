"""RFC 6238 TOTP enrollment/verification and backup-code issuance.

**Enrollment.** `provision_secret()` generates a fresh random base32 secret
(`pyotp.random_base32()`, 160 bits per RFC 4226/6238's own recommendation)
and returns both the raw secret (to be encrypted and stored via
`app.core.crypto.encrypt_totp_secret` -- callers must never store the raw
value) and a `otpauth://` provisioning URI an authenticator app can consume
as a QR code.

**Verification.** `verify_code()` wraps `pyotp.TOTP.verify` with `valid_window=1`
-- accepts the current 30-second step and one step of clock drift either
direction (a total tolerance of one step, ~30s, each way), a standard,
bounded allowance for client/server clock skew that does not meaningfully
weaken the six-digit code's brute-force resistance.

**Backup codes.** Ten single-use codes, each `secrets.token_hex(5)` (10 hex
characters, 40 bits of entropy -- generous for a code the user copies down
once and uses at most once), generated together at enrollment. Callers hash
each with `app.core.security.hash_backup_code` before persisting
(`UserBackupCode.code_hash`); this module never sees or returns a hash, only
the plaintext codes to show the user exactly once.
"""

import secrets

import pyotp

ISSUER_NAME = "Sirius"
BACKUP_CODE_COUNT = 10


def provision_secret(account_email: str) -> tuple[str, str]:
    """Returns (raw_secret, provisioning_uri)."""
    secret = pyotp.random_base32()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=account_email, issuer_name=ISSUER_NAME)
    return secret, uri


def verify_code(raw_secret: str, code: str) -> bool:
    totp = pyotp.TOTP(raw_secret)
    return bool(totp.verify(code, valid_window=1))


def generate_backup_codes(count: int = BACKUP_CODE_COUNT) -> list[str]:
    return [secrets.token_hex(5) for _ in range(count)]
