"""PushSubscription: one row per registered browser Web Push subscription
(RFC 8030), Module 20.

**Not RLS-scoped -- deliberately, the same "identity axis" reasoning
`0003_rls`'s own docstring already gives for `user`/`role`/
`user_backup_code`, extended here.** This table is written and deleted
by exactly one actor for a given row -- the account holder managing
their own browser's subscription, enforced at the *application layer*
by `POST`/`DELETE /notifications/subscribe` sourcing `user_id`
exclusively from the session (the same "trust the session, never the
body" rule `ChangeNameRequest`/`ChangePasswordRequest` already
establish) -- but it is *read* by code that is not the subscription
owner's own request at all: a counselor's `POST /applicants` call needs
to read a *different* user's (the assigned counselor's own, or every
`SUPER_ADMIN`/`ADMISSIONS_MANAGER`'s) subscriptions to notify them; a
`FINANCE_STAFF` member's `POST /finance/payment-claims` call needs to
read `FINANCE_MANAGER`'s own subscriptions. An RLS policy scoped to
"only your own subscriptions" would make every one of those legitimate
system-triggered reads either see zero rows (silently sending no
notification, indistinguishable from success) or need the same
dedicated-elevated-scope workaround Module 19's own duplicate-detection
fix already established for an analogous cross-user read -- reusing
that same workaround here, table by table, would eventually turn "RLS
covers everything" into ceremony around a table where the real
protection is a one-line application-layer identity check, not a
database policy. `password_reset_token`'s own docstring makes
structurally the same call for the same reason (a table read by code
that is not the row's own authenticated actor); this table follows
that precedent rather than reopening the question.

`endpoint` is globally unique per real browser subscription (the push
service's own delivery URL) -- `UNIQUE` at the database, and the
subscribe endpoint upserts on a collision (same browser re-subscribing,
e.g. after a page reload, returns the identical `endpoint` from
`pushManager.subscribe()`) rather than rejecting a second row for what
is, from the push service's own point of view, the same subscription.

`p256dh`/`auth` are the two public keys `pywebpush`'s `webpush()` needs
to encrypt a payload for this specific subscription (RFC 8291) --
opaque, base64url-encoded strings the browser generates and this table
stores verbatim, never decoded or interpreted server-side.
"""

import uuid
from datetime import datetime

from sqlalchemy import UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPKMixin
from app.models.types import fk_uuid


class PushSubscription(UUIDPKMixin, Base):
    __tablename__ = "push_subscription"
    __table_args__ = (UniqueConstraint("endpoint", name="uq_push_subscription_endpoint"),)

    user_id: Mapped[uuid.UUID] = mapped_column(*fk_uuid("user.id"), nullable=False)
    endpoint: Mapped[str] = mapped_column(nullable=False)
    p256dh: Mapped[str] = mapped_column(nullable=False)
    auth: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), nullable=False)
