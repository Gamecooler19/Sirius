"""Password hashing (Argon2id) and TOTP-backup-code hashing.

**Argon2id parameters.** `argon2-cffi`'s `PasswordHasher` defaults
(`time_cost=3`, `memory_cost=65536` KiB = 64 MiB, `parallelism=4`,
`hash_len=32`, `salt_len=16`) are used as-is: they sit at OWASP's current
recommended range for Argon2id (OWASP Password Storage Cheat Sheet:
m=19 MiB..64 MiB depending on variant, t=2-3, p=1-4), and this deployment
has no unusual latency or memory constraint that would justify deviating
from a reviewed default.

The same hasher is reused for TOTP backup codes (`app.models.user.
UserBackupCode.code_hash`) -- a backup code is a credential exactly like a
password, and deserves the same at-rest protection, not a faster/weaker
hash on the theory that it is "only" a backup code.
"""

import contextlib

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()

# A hash of an unused, fixed password, computed once at import time. Used by
# the login endpoint's dummy-verification path so that verifying a password
# against a nonexistent user takes the same shape of work as verifying one
# against a real user does -- a timing side channel that would otherwise
# let an attacker distinguish "no such user" from "wrong password" by
# response latency alone.
_DUMMY_HASH = _hasher.hash("no-such-user-dummy-verification-target")


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """`InvalidHashError` -- not only `VerifyMismatchError` -- is caught
    here and treated as a failed verification, not an unhandled exception.
    A malformed stored hash (corrupt data, a truncated write, a value that
    was never actually an Argon2id hash) must fail closed as "wrong
    password" the same way a real mismatch does, rather than surfacing a
    500 to the login endpoint's caller -- confirmed as a real gap by this
    module's own live-stack verification, which hit exactly this path
    against a hash corrupted in transit by shell-escaping in a manual test
    insert, not a hypothetical.
    """
    try:
        _hasher.verify(hashed, plain)
        return True
    except (VerifyMismatchError, InvalidHashError):
        return False


def verify_password_dummy(plain: str) -> None:
    """Run a real Argon2id verification against a fixed dummy hash. Called
    on the unknown-email path in the login endpoint so that path does the
    same shape of cryptographic work as the found-user path. The result is
    discarded; it will always be a mismatch.
    """
    with contextlib.suppress(VerifyMismatchError):
        _hasher.verify(_DUMMY_HASH, plain)


def hash_backup_code(code: str) -> str:
    return _hasher.hash(code)


def verify_backup_code(code: str, hashed: str) -> bool:
    try:
        _hasher.verify(hashed, code)
        return True
    except VerifyMismatchError:
        return False


def hash_reset_token(token: str) -> str:
    """Module 16: password-reset tokens are hashed with the exact same
    Argon2id hasher as everything else in this module (password,
    backup codes) -- a distinct function name for readability at the
    call site, not a distinct algorithm or set of parameters.
    """
    return _hasher.hash(token)


def verify_reset_token(token: str, hashed: str) -> bool:
    try:
        _hasher.verify(hashed, token)
        return True
    except (VerifyMismatchError, InvalidHashError):
        return False
