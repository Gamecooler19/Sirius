"""Shared Valkey (Redis-protocol) client factory.

One client per running event loop -- `redis.asyncio.Redis.from_url`
internally manages a connection pool, so there is no reason for each module
to open its own connection. Keyed by the loop object itself via
`WeakKeyDictionary` rather than `id(loop)`, since CPython can recycle a
garbage-collected object's integer id -- a dict keyed by plain `id()` could
hand a dead loop's client to an unrelated new loop if the id happens to be
reused; a `WeakKeyDictionary` avoids that by holding the loop object itself
(weakly) as the key.
"""

import asyncio
from weakref import WeakKeyDictionary

from redis.asyncio import Redis

from app.core.config import get_settings

settings = get_settings()

_clients: "WeakKeyDictionary[asyncio.AbstractEventLoop, Redis]" = WeakKeyDictionary()


def get_valkey() -> Redis:
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None:
        client = Redis.from_url(settings.VALKEY_URL, decode_responses=True)
        _clients[loop] = client
    return client
