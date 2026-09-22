"""Async SQLAlchemy engine and per-request session factory.

DATABASE_URL points at PgBouncer running in **transaction pooling** mode
(ADR-01). Three constraints follow directly from that, and none are optional:

1. asyncpg's prepared-statement cache is disabled on both the connection
   (`statement_cache_size=0`, `prepared_statement_cache_size=0` in
   connect_args) and the DSN itself (`?prepared_statement_cache_size=0`).
   Without this, asyncpg caches a prepared statement against a specific
   server connection PgBouncer does not guarantee it gets back, producing an
   intermittent `prepared statement "__asyncpg_stmt_x__" does not exist`
   error under load -- invisible in local single-connection testing.

2. `poolclass=NullPool`. PgBouncer *is* the connection pool. Stacking
   SQLAlchemy's own pool in front of it means two layers fighting over the
   same finite set of server connections for no benefit.

3. Every function below opens one transaction per request/scope and commits
   (or rolls back) at the end, never leaving an autocommit session floating
   outside a transaction boundary. `open_scoped_session` issues `SET LOCAL`
   for every RLS GUC (`app.actor_id`, `app.actor_role`, `app.client_ip`)
   inside that transaction. `SET LOCAL` only ever applies for the remainder
   of the *current transaction* -- a bare `SET` would bind to the underlying
   server connection itself, and because PgBouncer hands that same server
   connection to a completely different client on the next transaction, a
   bare `SET` would leak one actor's identity/role into another client's
   next, unrelated request. Do not remove the per-request transaction
   boundary, and do not replace `SET LOCAL` with `SET`, without re-reading
   this comment.

   `SET LOCAL x = <value>` cannot be parameterized directly -- Postgres's
   `SET` statement does not accept bind parameters over the extended query
   protocol asyncpg uses. `set_config(name, $1, true)` is the parameterized
   equivalent (`true` = local to the current transaction, exactly like `SET
   LOCAL`), and is what `open_scoped_session` uses below, so no GUC value is
   ever built by string interpolation.
"""

import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()

_dsn = settings.DATABASE_URL
_dsn += "&" if "?" in _dsn else "?"
_dsn += "prepared_statement_cache_size=0"

engine = create_async_engine(
    _dsn,
    poolclass=NullPool,
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    },
    echo=False,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: one transaction per request, **no RLS scope set**.

    This is the unscoped primitive. Any route that touches an
    RLS-protected table must use `open_scoped_session` (directly, or via
    `get_scoped_session` in `app.core.deps`) instead -- an unscoped session
    sees zero rows on every RLS-protected table by design (fail closed), not
    all of them, because the role-comparison GUC is unset.
    """
    async with async_session_factory() as session, session.begin():
        yield session


@asynccontextmanager
async def open_scoped_session(
    actor_id: uuid.UUID | None,
    actor_role: str | None = None,
    client_ip: str | None = None,
) -> AsyncIterator[AsyncSession]:
    """Open one transaction, set the RLS GUCs inside it, yield the session.

    `actor_id=None`/`actor_role=None` is a deliberate, supported case -- it
    exercises the fail-closed path: no `SET LOCAL` is issued for that GUC,
    `current_setting(name, true)` evaluates to NULL (or, on a pooled backend
    that has previously had the GUC set, an empty string -- see ADR-01's
    `NULLIF` note) inside the transaction, and every RLS policy comparing
    against it evaluates to NULL (false), so the session sees zero rows on
    every scoped table rather than every row.
    """
    async with async_session_factory() as session, session.begin():
        if actor_id is not None:
            await session.execute(
                text("SELECT set_config('app.actor_id', :v, true)"), {"v": str(actor_id)}
            )
        if actor_role is not None:
            await session.execute(
                text("SELECT set_config('app.actor_role', :v, true)"), {"v": actor_role}
            )
        if client_ip is not None:
            await session.execute(
                text("SELECT set_config('app.client_ip', :v, true)"), {"v": client_ip}
            )
        yield session
