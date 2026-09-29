"""seed_superadmin

Revision ID: 0016_seed_superadmin
Revises: 0015_finance_fee_due
Create Date: 2026-09-29

Module 23: seeds exactly one real login for a fresh, empty database --
`SUPER_ADMIN` Pradyumn Tandon (`ptandon3@hawk.illinoistech.edu`) -- the
same "seed once, first-run only" shape migration `0005_seed_roles`
already established for the six roles, applied here to a single `user`
row instead of a fixed lookup table.

**Idempotency.** `email` carries `uq_user_email` (migration 0002), so
this migration checks for an existing row with this exact email before
inserting, the same guard `0005_seed_roles` gets for free from
`ON CONFLICT (code) DO NOTHING` -- a plain `SELECT` + conditional
`INSERT` here instead, since a bare `ON CONFLICT (email) DO NOTHING`
would silently swallow the one case worth distinguishing from "already
seeded": a *different* SUPER_ADMIN row somehow already existing at this
exact email with different data would look identical to a successful
idempotent no-op. Re-running `alembic upgrade head` against a database
that already has this seed is therefore a genuine no-op, not an error
and not a duplicate row -- verified live (see the module's own report).

**No password or password hash is ever a literal in this file.** A
migration is committed source code that runs unmodified on every future
fresh deployment of this project, forever -- unlike `deploy/.env`, which
is per-deployment and gitignored. Hardcoding even a hash here would mean
every fresh install of this codebase, anywhere, shares byte-for-byte the
same Argon2id hash for its first SUPER_ADMIN account, which defeats the
per-deployment salt Argon2id already provides and (worse) means a leak
of *this specific hash* from any one deployment's `audit_log`/backup
compromises the seed account's password-guessing resistance for every
other deployment that ever ran this same migration. Instead:

1. `SUPERADMIN_INITIAL_PASSWORD` is read from the environment at
   migration-run time only (`os.environ`, required -- this migration
   raises immediately, before touching the database, if it is unset).
   It is never logged, never written to any column, and never returned
   from this module.
2. It is hashed with `app.core.security.hash_password` -- the exact same
   Argon2id `PasswordHasher` instance (same `time_cost`/`memory_cost`/
   `parallelism`/`salt_len`) `POST /auth/login`'s own `verify_password`
   call and every other password/backup-code/reset-token hash in this
   codebase already uses (see that module's own docstring) -- not a
   hand-rolled or differently-parameterized hash. `alembic/env.py`
   already puts `api/` on `sys.path` and imports from `app.*` for
   `Settings`, so importing `app.core.security` here follows the exact
   same established precedent, not a new one.
3. Only the resulting hash is written to `user.password_hash`. The
   plaintext value is never persisted anywhere by this migration; the
   only place it exists after this migration runs is wherever the
   deployer's own process put it into `SUPERADMIN_INITIAL_PASSWORD` in
   the first place (`deploy/.env`, gitignored, exactly like every other
   secret this stack generates).

**`totp_enabled=False` by construction, matching `POST /users`' own
reasoning verbatim (see `app.routers.users.create_user`'s own
docstring).** This migration does not provision a TOTP secret, does not
pre-confirm enrollment, and does not special-case this account's first
login in any way -- `user.totp_enabled` already `server_default`s to
`false` (migration 0002), so leaving it alone here is what lets
`POST /auth/login`'s own existing `totp_enrollment_required` branch
(keyed off `MANDATORY_TOTP_ROLES`, which `SUPER_ADMIN` is a member of --
`app.models.enums`) drive this account through the real
`/auth/totp/enroll/start` + `/confirm` flow on its very first login,
identical to any other mandatory-TOTP account this project has ever
created, seeded or admin-created alike.

**`is_active=True`.** Also just the column's own `server_default`
(`true`, migration 0002) -- stated explicitly here (rather than omitted
from the INSERT and left to the default) only so this migration's own
intent reads unambiguously next to `totp_enabled`, not because a
different value was ever considered.

**`activated_at` is left `NULL`.** This is a fresh account that has
never set its own password through the real activation/reset flow --
see `User.activated_at`'s own docstring: `NULL` here means exactly that,
the identical state `POST /users`-created accounts start in before their
welcome link is redeemed. Unlike a `POST /users`-created account,
though, this seed *does* have a real, usable password from the moment
this migration runs (the hash written to `password_hash` corresponds to
the real `SUPERADMIN_INITIAL_PASSWORD`, not an unguessable, thrown-away
value) -- `activated_at` is a display-only "has this account completed
the self-service activation flow" signal (`UsersPage`'s own "pending
activation" indicator), not itself a login gate, so a login working
immediately while `activated_at` stays `NULL` is consistent with every
other place this column is documented, not a contradiction.
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

from app.core.security import hash_password

# revision identifiers, used by Alembic.
revision: str = "0016_seed_superadmin"
down_revision: str | None = "0015_finance_fee_due"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_EMAIL = "ptandon3@hawk.illinoistech.edu"
SEED_FULL_NAME = "Pradyumn Tandon"
SEED_ROLE_CODE = "SUPER_ADMIN"


def upgrade() -> None:
    conn = op.get_bind()

    # Idempotency guard, checked before anything else (including reading
    # the environment) -- a re-run against a database that already has
    # this seed does not require SUPERADMIN_INITIAL_PASSWORD to even be
    # set, matching 0005_seed_roles' own "re-running is a safe no-op"
    # contract.
    existing = conn.execute(
        text('SELECT id FROM "user" WHERE email = :email'),
        {"email": SEED_EMAIL},
    ).scalar_one_or_none()
    if existing is not None:
        return

    raw_password = os.environ.get("SUPERADMIN_INITIAL_PASSWORD")
    if not raw_password:
        raise RuntimeError(
            "SUPERADMIN_INITIAL_PASSWORD must be set in the environment for "
            "migration 0016_seed_superadmin to run against a fresh database "
            "-- see deploy/.env.example."
        )

    # Real Argon2id hash, the exact same hasher every other password in
    # this codebase uses (see this migration's own module docstring).
    # The plaintext value is used exactly once, here, and never stored.
    password_hash = hash_password(raw_password)

    role_id = conn.execute(
        text('SELECT id FROM "role" WHERE code = :code'),
        {"code": SEED_ROLE_CODE},
    ).scalar_one_or_none()
    if role_id is None:
        # Cannot happen on any database that ran 0005_seed_roles first
        # (this migration's own down_revision chain guarantees it did),
        # but fail loudly rather than inserting a user with a dangling
        # role_id if that invariant is ever somehow violated.
        raise RuntimeError(
            f"role '{SEED_ROLE_CODE}' not found -- 0005_seed_roles must run "
            "before 0016_seed_superadmin."
        )

    # "user"/"role" carry no RLS policy at all (ADR-03, the identity-axis
    # exception migration 0003_rls's own docstring documents) -- unlike
    # 0015_finance_fee_due's own backfill, no SET LOCAL app.actor_role is
    # needed here for this INSERT to actually affect a row.
    conn.execute(
        text(
            """
            INSERT INTO "user"
                (email, full_name, password_hash, role_id, totp_enabled, is_active)
            VALUES
                (:email, :full_name, :password_hash, :role_id, false, true)
            """
        ),
        {
            "email": SEED_EMAIL,
            "full_name": SEED_FULL_NAME,
            "password_hash": password_hash,
            "role_id": role_id,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text('DELETE FROM "user" WHERE email = :email'), {"email": SEED_EMAIL})
