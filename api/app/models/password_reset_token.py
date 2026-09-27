"""Password-reset token (Module 16): one row per issued self-service
password-reset request.

Stored hashed (argon2id via `app.core.security.hash_backup_code` -- the
same hasher every other single-use credential in this codebase already
uses for `UserBackupCode.code_hash`), never the raw token -- a token
the server could reproduce in plaintext from a database read is a
credential a database leak turns directly into an account takeover for
every account with a pending reset request, the exact same reasoning
`UserBackupCode`'s own docstring already establishes for backup codes.

`expires_at`: a fixed, short window (`app.routers.auth`'s own
`PASSWORD_RESET_TOKEN_TTL_MINUTES`) from issuance, checked on every
`POST /auth/reset-password` attempt.

`used_at`: single-use, the same `IS NULL`-checked-then-stamped pattern
`UserBackupCode.used_at` already establishes -- a reset link is good for
exactly one successful password change, never replayable.

Not RLS-scoped: like `user`/`user_backup_code` (ADR-03's identity axis),
this table exists to authenticate an as-yet-unauthenticated request --
`POST /auth/forgot-password` and `POST /auth/reset-password` are both
unauthenticated by definition (that is the entire point of a
self-service password-reset flow), so there is no `app.actor_role`/
`app.actor_id` GUC set when either endpoint's queries run, structurally
the same reason `user` itself cannot be RLS-scoped.
"""

import uuid
from datetime import datetime

from sqlalchemy import UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin
from app.models.types import fk_uuid


class PasswordResetToken(UUIDPKMixin, Base):
    __tablename__ = "password_reset_token"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_password_reset_token_hash"),)

    user_id: Mapped[uuid.UUID] = mapped_column(*fk_uuid("user.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
