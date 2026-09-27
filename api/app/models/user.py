"""User: application accounts. RBAC via `role_id`; TOTP two-factor state
lives on this table directly (`totp_secret_encrypted`, `totp_enabled`)
rather than a separate one-row-per-user side table, since every user has at
most one TOTP secret and the two columns are always read together with the
rest of the identity row during login.

`totp_secret_encrypted`: the raw RFC 6238 secret, Fernet-encrypted at rest
(`app.core.crypto`) with a key distinct from the database itself -- a
database dump or read-only replica leak does not, by itself, hand over every
account's live TOTP seed. Decrypted only inside `app.core.totp` at the
moment a code is verified or provisioned.

`is_active`: administrative kill switch, checked on every authenticated
request (not only at login) by the RBAC dependency, so deactivating an
account takes effect on the very next request rather than waiting for a
session to expire.

`activated_at` (Module 17, nullable): `NULL` for an admin-created account
that has never yet set a real, self-chosen password -- see
`app.routers.users.create_user`'s own docstring for why such an account's
`password_hash` is a real Argon2id hash of an unguessable, never-revealed
random value rather than a null/sentinel column, and why that alone
(not this column) is what makes login genuinely impossible in that
window. This column exists for a narrower purpose: telling an
already-active, never-activated account (an admin-created account whose
welcome link nobody has clicked yet) apart from an ordinary already-
activated account, for display purposes (`UsersPage`'s own "pending
activation" indicator) -- `is_active` alone cannot make that distinction,
since both states have `is_active=True` by construction (see
`create_user`'s own docstring for why deactivation is deliberately kept
a separate, unrelated concept from activation). Stamped the first time
`POST /auth/reset-password` succeeds for this account, whether that
call redeemed the original welcome token or an ordinary later
forgot-password token -- both redemption paths are identical code (see
`PasswordResetToken`'s own docstring), so this column answers "has this
account ever successfully set a password," not "was it specifically the
welcome flow." Existing accounts from before this module (every
manually-seeded and Module-15-admin-created account, which always had
an admin-supplied real password from the start) are backfilled to their
own `created_at` by this module's own migration, so none of them are
misread as pending.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPKMixin
from app.models.types import fk_uuid


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "user"
    __table_args__ = (UniqueConstraint("email", name="uq_user_email"),)

    email: Mapped[str] = mapped_column(nullable=False)
    full_name: Mapped[str] = mapped_column(nullable=False)
    password_hash: Mapped[str] = mapped_column(nullable=False)

    role_id: Mapped[uuid.UUID] = mapped_column(*fk_uuid("role.id"), nullable=False)

    totp_secret_encrypted: Mapped[str | None] = mapped_column(nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(nullable=True)


class UserBackupCode(UUIDPKMixin, Base):
    """One of the ten single-use TOTP backup codes issued at enrollment.

    Stored hashed (argon2id, the same hasher as `password_hash`) rather than
    plaintext or reversibly encrypted -- a backup code is a credential, and a
    credential the server can produce in plaintext again is one a database
    leak turns directly into an authentication bypass. `used_at` makes each
    code single-use: set the instant it is consumed, checked (`IS NULL`) on
    every verification attempt.
    """

    __tablename__ = "user_backup_code"
    __table_args__ = (UniqueConstraint("user_id", "code_hash", name="uq_backup_code_per_user"),)

    user_id: Mapped[uuid.UUID] = mapped_column(*fk_uuid("user.id"), nullable=False)
    code_hash: Mapped[str] = mapped_column(nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
