"""Account-action token (Module 16, extended Module 17): one row per
issued single-use, hashed, expiring token proving control of either the
account itself (a password action) or a target mailbox (an email-change
confirmation).

**Table name kept as `password_reset_token` deliberately, not renamed.**
This table now serves three call sites -- `POST /auth/forgot-password`'s
own reset token, `POST /users`' welcome/account-activation token
(Module 17), and `POST /auth/change-email`'s confirmation token
(Module 17) -- but all three share the exact same shape (`user_id`,
`token_hash`, `expires_at`, `used_at`) and the exact same redemption
mechanics (hash-compare against every unexpired/unused row, mark
`used_at` on success). Renaming the table to something more generic
would touch every existing reference to it (models, routers, this
module's own migration history, the Module 16 report) for a purely
cosmetic gain; reusing it as-is, with `new_email` as the one field that
distinguishes an email-change token from a password-type token, is the
literal "reuse the model and hashing helpers, don't fork them"
instruction this module (17) was given.

Stored hashed (argon2id via `app.core.security.hash_reset_token`, the
same hasher every other single-use credential in this codebase already
uses), never the raw token -- a token the server could reproduce in
plaintext from a database read is a credential a database leak turns
directly into an account takeover for every account with a pending
action, the exact same reasoning `UserBackupCode`'s own docstring
already establishes for backup codes.

`expires_at`: a fixed window from issuance (30 minutes for password
reset/email-change tokens, 24 hours for welcome/activation tokens --
see `app.routers.auth`'s and `app.routers.users`' own TTL constants for
why the two windows differ), checked on every redemption attempt.

`used_at`: single-use, the same `IS NULL`-checked-then-stamped pattern
`UserBackupCode.used_at` already establishes -- a token is good for
exactly one successful action, never replayable.

`new_email` (Module 17, nullable): `NULL` for a password-type token
(password reset or welcome/initial-activation -- both are redeemed the
same way, by `POST /auth/reset-password`, and are indistinguishable
from that endpoint's point of view; see `app.routers.users.create_user`'s
own docstring for why a welcome token deliberately reuses the password-
reset redemption path rather than getting a second one). Non-`NULL` for
an email-change token, which carries the new address it will apply on
confirmation and is redeemed only by the distinct
`POST /auth/confirm-email-change` (a structurally different action --
setting `email`, not `password_hash` -- that cannot share
`reset-password`'s own redemption code). Both redemption endpoints
filter on this column (`IS NULL` / `IS NOT NULL` respectively) so a
token issued for one purpose can never be redeemed through the other
endpoint.

Not RLS-scoped: like `user`/`user_backup_code` (ADR-03's identity axis),
this table exists to authenticate or confirm an as-yet-unauthenticated-
for-this-specific-action request -- `POST /auth/forgot-password`,
`POST /auth/reset-password`, and `POST /auth/confirm-email-change` are
all unauthenticated by definition (the whole point of a self-service
token redemption is that it doesn't require an existing session), so
there is no `app.actor_role`/`app.actor_id` GUC set when any of their
queries run, structurally the same reason `user` itself cannot be
RLS-scoped. `POST /auth/change-email` (the *request* side of the
email-change flow) is authenticated, but the row it writes is read back
by the unauthenticated confirm endpoint, so the table as a whole still
cannot carry an RLS policy without breaking that read.
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
    new_email: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
