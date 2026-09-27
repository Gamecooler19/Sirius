"""Shared Pydantic type for every timestamp field this API serializes to
JSON (Module 21 audit finding, fixed here).

**The real, live-confirmed defect this closes.** Every timestamp column
in this schema is `timestamp without time zone` (`app.models.base.
TimestampMixin`'s own docstring notwithstanding -- it says "timestamptz"
but the actual migrations declare every one of these columns without a
timezone, and the whole codebase's own convention, e.g.
`app.routers.auth`'s repeated `datetime.now(timezone.utc).replace(
tzinfo=None)`, is "store a naive datetime that is *implicitly* UTC").
Pydantic's default `datetime` JSON serialization for a naive value
(`.isoformat()`) produces a string with **no `Z` suffix and no `+00:00`
offset** -- e.g. `"2026-09-27T15:20:40.709030"`. Confirmed live: a
browser's own `new Date("2026-09-27T15:20:40.709030")` does not
interpret that string as UTC (the correct meaning) -- the ECMAScript
date-parsing spec treats an offset-less ISO string as **local time**,
so `toLocaleString()` on that same `Date` object silently printed
`"3:20:40 pm"` for an event that genuinely happened at `20:50:40 IST`
(`+05:30`), a full 5.5 hours off with no error, warning, or visual
indication anything was wrong -- every timestamp displayed anywhere in
this app (payment-claim submission times, status-history events,
applicant `created_at`/`updated_at`, import-batch timestamps, user
`last_login_at`/`activated_at`) was silently wrong by whatever offset
separates the viewing browser's own timezone from UTC.

**Fix: serialize with an explicit UTC marker, not a change to storage
or to any frontend file.** `UtcDatetime` is a drop-in replacement for
a plain `datetime` type annotation on any *response* schema field
(never a request field -- an incoming request body's datetime, if this
codebase ever accepts one as a field rather than deriving every
timestamp server-side, is a parsing concern, not a serialization one).
`_serialize_utc` attaches `timezone.utc` to a naive value before
calling `.isoformat()`, producing e.g.
`"2026-09-27T15:20:40.709030+00:00"` -- a value `new Date()` parses
correctly in every timezone, with zero frontend changes required, since
every existing `new Date(...).toLocaleString()` call site already does
the right thing once the string itself unambiguously says what
timezone it is in. A datetime that somehow already carries a timezone
(defensive, not expected to occur given this codebase's own
naive-UTC convention) is left untouched, not double-converted.
"""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import PlainSerializer


def _serialize_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


UtcDatetime = Annotated[datetime, PlainSerializer(_serialize_utc, return_type=str)]
