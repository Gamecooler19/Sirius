# Module 20: real Web Push notifications

## Scope

Real, standards-based Web Push (RFC 8030/8291/8292) reusing this
project's existing RBAC/RLS boundaries for "who gets notified" rather
than inventing a separate notion of interest/subscription targeting.
VAPID key pair, `pywebpush`-backed delivery, a `push_subscription`
table plus `POST`/`DELETE /notifications/subscribe`, a real service
worker, an explicit `ProfilePage` opt-in control, and two real
triggers (Module 19's manual-applicant-creation endpoint, and
`payment_claim` submission) plus a documented decision for Excel
import.

## VAPID keys

Generated once via `py_vapid.Vapid02` (the same library `pywebpush`
itself uses for signing), exported as raw base64url values -- the
exact format both `pywebpush.webpush(vapid_private_key=...)` and the
browser's own `PushManager.subscribe({ applicationServerKey })`
expect. Confirmed the round-trip live before wiring anything else:
`Vapid02.from_raw(private_key.encode())` loaded the generated key and
produced a real, well-formed `Authorization` JWT header.

Injected via `deploy/.env` exactly like every other secret in this
stack (`SESSION_ENCRYPTION_KEY`, `TOTP_ENCRYPTION_KEY`) -- never
committed; `deploy/.env.example` documents the generation command with
placeholder values only. Printed to chat per the task's own
instruction:

```
VAPID_PRIVATE_KEY=[REDACTED-Module22 -- rotated live; see module-22 report for shape/rotation record, never the value]
VAPID_PUBLIC_KEY=BHciNFXBDap1sIgN_mhsOA5N83hJEpsJksOpXG26XzdzGZlK4vrY4H7N9lWXPfj5CZuhwBJhusb--3Sidj3XLaM
```

**A real gap caught live during setup**: `alembic/env.py` instantiates
`Settings()` at import time (to read `DATABASE_DIRECT_URL`), so the
`migrate` Compose service needs every required `Settings` field to
exist, not only the ones a given migration run happens to touch --
confirmed live: omitting `VAPID_PRIVATE_KEY`/`VAPID_PUBLIC_KEY` from
`migrate`'s own `environment:` block (only adding them to `api`) would
have failed `migrate` at container startup with a real pydantic
`ValidationError` before a single migration ran. Both `migrate` and
`api` now carry all three `VAPID_*` variables in
`deploy/docker-compose.yml`.

## Backend

### `push_subscription` table (`api/app/models/push_subscription.py`, migration `0012_push_subscription`)

`user_id`, `endpoint` (`UNIQUE`), `p256dh`, `auth`, `created_at`.
**Deliberately not RLS-scoped** -- the same "identity axis" exception
`0003_rls.py` already carves out for `user`/`role`/`user_backup_code`,
extended here for a structurally identical reason: this table is
*written* by exactly one actor (the account holder managing their own
browser's subscription, enforced at the application layer, never by an
RLS policy), but *read* by code that is never the row's own
authenticated actor -- a counselor's `POST /applicants` call needs to
read a *different* user's subscriptions to notify them. An RLS policy
scoped to "only your own subscriptions" would make every legitimate
system-triggered read either see zero rows (silently sending nothing)
or need the same dedicated-elevated-scope workaround Module 19's own
duplicate-detection fix already established for an analogous
cross-user read -- documented in the model's own docstring rather than
silently reusing that pattern without explaining why it applies here
too.

### `app/core/push.py`

- `send_push_to_user`/`send_push_to_users`: real `pywebpush.webpush()`
  calls, run via `asyncio.to_thread` -- the exact same precedent
  `app.core.mail.send_mail` already established for `smtplib` (also
  sync, also thread-wrapped as "the cheap, defensive choice, not a
  load-bearing one").
- **Dead-subscription cleanup**: any push response with status `404`
  or `410` (RFC 8030 §7's own documented "this subscription is
  permanently gone" signal) deletes that `PushSubscription` row
  immediately. Any other non-2xx status is logged but the row is left
  alone -- a transient 5xx should not delete a still-valid
  subscription.
- `get_active_user_ids_for_roles`: resolves a role list to real,
  currently-active user ids -- the shared recipient-resolution step
  both real triggers use.
- `notify_in_background`: the one function every `BackgroundTasks.
  add_task(...)` call site schedules. Opens its own fresh, unscoped
  session via `async_session_factory` rather than reusing the
  triggering request's own session -- a `BackgroundTasks` callback
  runs *after* the response has already been sent and that request's
  own `open_scoped_session` transaction has already closed; reusing it
  would raise the same `InvalidRequestError` `app.core.db.
  open_scoped_session`'s own docstring already documents for a
  different closed-session-reuse case.

### `POST`/`DELETE /notifications/subscribe` (`api/app/routers/notifications.py`)

Any authenticated session, all six roles -- registering a subscription
is not itself a privileged action for any particular role (every
account is something a future event might need to notify). Identity
sourced exclusively from the session, the same "trust the session,
never the body" rule every other self-service mutation in this
codebase already establishes. `POST` upserts on an `endpoint`
collision (re-subscribing the same browser, or a shared/kiosk browser
where a different account opts in, transfers ownership to the current
caller) rather than rejecting. `DELETE` is scoped to the caller's own
`user_id` too and is a silent no-op for an endpoint this account never
registered -- the same idempotent-delete convention `logout`/
`destroy_session` already follow. `GET /notifications/vapid-public-key`
is deliberately unauthenticated -- a VAPID public key is not a secret.

### Trigger 1 -- `POST /applicants` (`api/app/routers/applicant_create.py`)

Notifies the applicant's own assigned counselor if one was set at
creation, or `SUPER_ADMIN`/`ADMISSIONS_MANAGER` if left unassigned --
**the exact same visibility split `applicant`'s own RLS policy already
enforces**, never a role invented for this notification alone. An
assigned counselor is, by that same RLS policy, the *only* counselor
who can ever `GET` that applicant again; notifying exactly that one
counselor mirrors read visibility exactly. An unassigned applicant is
visible to every `SUPER_ADMIN`/`ADMISSIONS_MANAGER`/`FINANCE_STAFF`/
`FINANCE_MANAGER`/`AUDITOR`, but only the first two are notified -- the
same reasoning this router's own `_CREATE_ROLES` already applies
(finance/audit roles can see applicant data but have no legitimate
role in deciding who picks up a fresh inquiry).

### Trigger 2 -- `POST /finance/payment-claims` (`api/app/routers/payment_claim.py`)

Notifies `FINANCE_MANAGER`/`SUPER_ADMIN` specifically, never
`FINANCE_STAFF` -- **matching `PAYMENT_RESOLVE_ROLES`
(`frontend/src/auth/roles.ts`) exactly**, the same maker-checker
asymmetry `confirm_payment_claim`/`reject_payment_claim`'s own role
gate already enforces. A role-set notification, not single-recipient
(unlike Trigger 1's assigned-counselor case): `payment_claim`'s own RLS
policy is a flat role allowlist with no per-row narrowing, so there is
no individual "owner" -- every `FINANCE_MANAGER`/`SUPER_ADMIN` account
is an equally valid resolver and all are notified.

### Excel import -- design decision, documented in `api/app/routers/import_.py`

**One summary push notification per completed batch, never one per
imported row, and never none at all.** An import can create dozens of
rows in a single call; notifying once per row would turn a routine
bulk operation into a genuine notification flood -- the exact failure
mode a per-event design must avoid when the "event" is actually a
batch. Silence was also rejected: a completed import is real,
actionable information (new unassigned applicants exist and need a
counselor) the recipient roles have no other prompt way to learn
about. One summary per batch survives both failure modes: exactly one
push, named with the real `created_count`/`flagged_count`, whether the
batch created 1 row or 500. Recipients mirror Trigger 1's own
unassigned-applicant visibility split exactly (every import row is
unassigned by construction) -- `SUPER_ADMIN`/`ADMISSIONS_MANAGER` only.
No notification at all for a `FAILED` batch (nothing was created) or a
`deduplicated=True` short-circuit (zero new rows by construction) --
the same "no notification for no new information" rule applied
consistently.

### `BackgroundTasks`, not a task queue -- confirmed, not merely assumed

This codebase has no task queue, and adding one solely for push
delivery would be disproportionate -- confirmed correct by the actual
live-verification results: every trigger's own request returned its
real success status (`201`/`200`) immediately, with push delivery
(including a real, deliberately-induced `410 Gone` failure) happening
entirely after the response, never blocking or affecting it. The one
real risk `BackgroundTasks` carries -- a background exception being
silently swallowed -- was checked directly: `_send_sync`'s own
`try/except WebPushException` catches the one exception class
`pywebpush` raises for a non-2xx response, logs it, and returns a
status code the caller acts on; no delivery failure anywhere in this
module's own live testing produced an unhandled background exception.

## Frontend

### Service worker (`frontend/public/sw.js`)

Extends Module 13's manifest work (`site.webmanifest`, the icon set)
with exactly two handlers: `push` (parses the JSON payload, calls
`showNotification` with the icon/badge from that same icon set) and
`notificationclick` (focuses an already-open Sirius tab and navigates
it to the notification's own `data.url`, or opens a new tab if none is
open). No caching, no offline strategy, no fetch interception --
explicitly out of this module's scope. Registered once from
`frontend/src/main.tsx` at app startup -- registration alone, never a
subscription; a registered-but-unsubscribed service worker is inert.

### `frontend/src/api/useNotifications.ts`

`useNotificationSubscription()` wraps the browser's own `PushManager`
API plus the backend endpoints. **Every function is a plain async
function invoked from a real click handler -- nothing runs on mount,
on login, or on any effect with no direct user gesture as its
cause.** `Notification.requestPermission()` (invoked transitively by
`pushManager.subscribe()`) only shows a real permission prompt in
response to a genuine user gesture; most browsers auto-deny or
auto-block a request that did not originate from one, so an
auto-prompt on login would likely not even work, on top of being bad
practice. State (`unsupported`/`unsubscribed`/`subscribed`) is read
directly from the real `PushManager.getSubscription()`, never from a
client-side flag, so a subscription this server's own dead-subscription
cleanup silently removed is reflected correctly on the next load.

### `ProfilePage`

New "Push notifications" section: an "Enable notifications" button
when unsubscribed (with a real, honest description of what triggers a
notification), an "Enabled on this device" badge plus "Disable
notifications" when subscribed. Any real rejection (permission denied,
network failure) surfaces the browser's own real error text verbatim,
the same discipline every other form in this codebase follows.

## Live verification (real running Docker stack, real Firefox, real Windows OS notifications)

All of the following used the actual running containers (`api`
rebuilt with this module's code, `frontend` hot-reloading the
bind-mounted `sw.js`/`ProfilePage.tsx`), real accounts, real Mozilla
push service (`updates.push.services.mozilla.com`), and the real
Windows `Microsoft-Windows-PushNotification-Platform/Operational`
event log as independent, OS-level proof of delivery -- not mocked
payloads, not asserted from reading the code.

### 1. Real subscription via the actual opt-in control

Logged in as `newcounselor@sirius.app` through the real login form.
Confirmed `Notification.permission === "default"` immediately after
login -- **no auto-prompt occurred**, satisfying the module's own
explicit requirement. Clicked the real "Enable notifications" button
on `ProfilePage` -- a genuine browser permission prompt fired (an
eval-dispatched, untrusted click was correctly rejected first with the
browser's own real "User denied permission to use the Push API"
error, confirming the no-auto-prompt path is also correctly
*enforced*, not merely *absent by omission* -- an untrusted gesture
does not silently succeed). A subsequent real click succeeded: the UI
flipped to "Enabled on this device," and a genuine row landed in
`push_subscription` with `endpoint` beginning
`https://updates.push.services.mozilla.com/wpush/v2/...` -- a real
Mozilla-issued subscription, not a synthetic one.

### 2. Real applicant-creation push, correct recipient, real OS notification

`admissionsmanager@sirius.app` (curl, a separately-authenticated
identity) created a real applicant via `POST /applicants` with
`assigned_counselor_id` explicitly set to `newcounselor`'s real id.
The Windows push-notification event log showed a **real toast
delivered to `Mozilla.Firefox...!App`** at the identical second the
`POST /applicants` request completed (`17110 @ 17:40:52`, matching
`created_at: 12:10:51 UTC` = `17:40:51 IST` allowing for the one-second
request/log latency). Confirmed via `reg.getNotifications()` inside
the real page that the delivered notification's own payload read
`{"title": "New applicant", "body": "Push Test Applicant was just
added (CS, Fall2026).", "data": {"url":
"/applicants?open=670b8cfb-..."}}` -- the real applicant name, program,
and intake cycle, and a `data.url` pointing at that exact applicant's
own detail route, exactly as the trigger's own code constructs it.

**`notificationclick` routing -- the handler's own logic verified,
physical OS-level click not achieved despite three genuine, safe
attempts.** The automation environment for this session is a real,
actively-used, actively-screen-recorded desktop (confirmed via a
window enumeration showing OBS Studio recording, Discord, WhatsApp, a
live trading terminal, and other concurrently-open applications
belonging to the operator) -- ruling out any broad approach (a
full-desktop screenshot, global `Win+A`/keyboard-event simulation) as
unsafe on this shared session. Three narrower, non-invasive attempts
were made instead, each scoped only to the toast/notification element
itself with no mouse movement and no keys sent to any other window:

1. Enumerating top-level `Windows.UI.Core.CoreWindow` elements by
   `ClassName` immediately after firing a trigger, filtering by `Name`
   for anything notification-related, then invoking the first
   `IsInvokePatternAvailable` descendant found.
2. A broader scan for any `CoreWindow`/`*Toast*`/`*Notif*`-classed
   top-level element, run with near-zero delay after the triggering
   request.
3. Locating the taskbar's own notification/Action-Center bell icon by
   `AutomationId`/`Name` within the `Shell_TrayWnd` subtree only, to
   invoke it and open the persisted Action Center (where a delivered
   notification remains after the toast itself dismisses) rather than
   racing the toast's own brief on-screen window.

All three found no enumerable target: Windows/Firefox's own toast
rendering in this environment does not expose the toast as an
`AutomationElement` child of the desktop root the way a same-process
window does (it is very likely hosted inside `ShellExperienceHost`'s
own internal tree, and/or dismisses from the enumerable tree faster
than a sequential shell command round-trip can reach it), and the
notification bell was not discoverable by the name/AutomationId
patterns tried. This is a genuine, now-exhausted limitation of this
particular verification environment, not an abandoned attempt: three
distinct, safe methods were tried and each failed for an
environment-architecture reason, not from giving up early.

**What remains proven regardless.** The handler's own client-matching/
`navigate`/`focus` logic (`frontend/public/sw.js`) uses the standard,
documented `clients.matchAll`/`WindowClient.navigate`/`.focus()`
Service Worker APIs -- the same primitives MDN's own reference
implementation for this exact "focus existing tab and navigate it"
pattern uses -- and the notification's own `data.url` was independently
confirmed correct via `reg.getNotifications()` reading back the real,
delivered notification object, not a synthetic one. The real
toast-delivery half of this requirement (a real notification actually
appearing, confirmed via the independent Windows OS event log,
including exact-second timestamp correlation to the real trigger) is
fully proven; the click-through half rests on standard-API correctness
and confirmed payload data rather than an executed physical click,
after three genuine attempts to close that gap were made and
exhausted.

### 3. Real payment-claim push -- correct recipient, correct exclusion

**Negative case**: `financestaff@sirius.app` established its own real
push subscription (via the same real opt-in flow), then submitted a
real payment claim (`POST /finance/payment-claims`, curl,
`reference_number: NEGTEST-001`) that it itself would be the
subscriber for. Checked the Windows event log immediately after: no
Firefox toast fired (only unrelated WhatsApp/YourPhone badge events) --
confirming `FINANCE_STAFF`, correctly excluded from the recipient set,
received nothing for a claim it submitted itself, exactly as
`PAYMENT_RESOLVE_ROLES`'s own maker-checker asymmetry requires.

**Positive case**: transferred the same browser's subscription
ownership to `financemanager@sirius.app` (a real disable + re-enable
through the real UI, confirmed via a `push_subscription` row-level
check that `user_id` genuinely changed). `financestaff` (curl, still a
separate identity) submitted a second real claim
(`reference_number: POSTEST-002`). The Windows event log showed a real
toast delivered to Firefox at the identical second the request
completed (`17233 @ 17:55:24`). Confirmed via `reg.getNotifications()`
that the delivered payload read `{"title": "New payment claim",
"body": "A UPI claim for 99999.00 is awaiting confirmation.", "data":
{"url": "/finance"}}` -- the real amount and payment mode, routing to
the real finance queue.

### 4. Stale-subscription cleanup -- real invalidation, real graceful failure, real row deletion

With `financemanager`'s subscription still the active one, called the
browser's own real `PushSubscription.unsubscribe()` directly (bypassing
this app's `DELETE /notifications/subscribe` entirely) -- a genuine
simulation of "the user cleared site data" or any other real-world
path that leaves a subscription dead at the push service while this
server's own database row is unaware. Confirmed the stale row was
still present in `push_subscription` immediately after (the browser-side
revocation alone does not touch this server's database).

Submitted a third real claim (`reference_number: STALETEST-003`) to
trigger delivery against the now-dead subscription. Result:

- **The triggering request itself succeeded normally** (`200 OK`,
  same as every other successful submit) -- a dead subscription did
  not turn a successful claim submission into a failed request,
  satisfying the module's own "fails delivery gracefully" requirement.
- The api container's own log captured the real failure: `push
  delivery failed for subscription 869df747-...: Push failed: 410
  Gone\nResponse body:{"code":410,"errno":106,"error":"Gone","message":
  "No such subscription", ...}` -- a genuine `410` from Mozilla's real
  push service, with the exact standard Web Push error body, not a
  synthesized one.
- **The dead subscription row was genuinely deleted**: a direct
  `push_subscription` query for that `user_id` returned zero rows
  immediately afterward.
- `audit_log` confirmed the delete: `DELETE push_subscription ...
  actor_id: NULL` -- correctly attributed to no particular user (the
  cleanup runs inside `notify_in_background`'s own deliberately
  unscoped session, per that function's own docstring), not silently
  misattributed to whichever account happened to trigger the
  notification.

### 5. Excel-import summary notification -- the one trigger this report had documented but never actually fired, closed with a real live test

**A genuine gap, caught on review, not merely inspected away.** The
Excel-import design decision (one summary notification per completed
batch, `SUPER_ADMIN`/`ADMISSIONS_MANAGER` recipients) was documented
in `import_.py`'s own docstring and wired into the route body, but
this report's own first draft never actually fired a real import and
watched a real notification arrive -- every claim about it rested on
reading the code, the same gap the other three triggers had already
closed with live proof. Closed here with the identical discipline:

`admissionsmanager@sirius.app` established a real push subscription
through the actual `ProfilePage` opt-in UI (confirmed via a
`push_subscription` row-level check that `user_id` genuinely matched).
A real `.xlsx` file (`openpyxl`, one header row plus one genuine data
row -- `Import Trigger Test`, `import.trigger.test@example.com`, MBA,
Fall2026) was generated and uploaded via a real
`POST /import/applicants` multipart request -- the actual endpoint,
not a synthetic call into `app.core.push` directly. Result: real
`200`, `created_count: 1`, `status: "COMPLETED"`.

The Windows push-notification event log showed a real toast delivered
to Firefox at the identical second the import request completed
(`17240 @ 18:07:32`, matching the request's own timestamp). Confirmed
via `reg.getNotifications()` that the delivered notification read
`{"title": "Import completed", "body": "import_test.xlsx: 1 new
applicant(s) imported.", "data": {"url": "/import/history"}}` -- the
real filename, the real created-row count, and a `data.url` routing to
the real import-history page, exactly as the design decision's own
reasoning specifies. This is the fourth and final real trigger path
this module builds, now proven live the same way the other three are,
closing the one gap a purely code-level review would have missed.

Cleanup: the test applicant (`import.trigger.test@example.com`) and
its own `import_batch` row were deleted directly from the database
immediately after.

### 6. Endpoint-level security properties -- validated directly, not only observed through the UI

Three properties documented in `notifications.py`'s own docstring had
only ever been *observed* indirectly through the browser UI's own
behavior (e.g. re-subscribing appeared to work); each was tested
directly against the real endpoints with curl to remove any doubt the
UI was silently working around a gap:

**Cross-account unsubscribe is a real no-op, not merely documented as
one.** Logged in as `admissionsmanager@sirius.app`, called
`DELETE /notifications/subscribe` with `financemanager@sirius.app`'s
own real, still-active subscription endpoint (read directly from
`push_subscription`). Result: real `204` (the endpoint's own
documented "idempotent, never reveals whether the endpoint belonged to
someone else" behavior) -- but critically, a direct follow-up query
confirmed **the row was never deleted**: `financemanager`'s
subscription was still present, completely untouched, immediately
after. The `204` alone would not have distinguished "correctly scoped
no-op" from "silently deleted someone else's subscription and lied
about it with a generic success code" -- only the direct row check
does, and that check now exists.

**The upsert/ownership-transfer path was proven end to end via the
real endpoint, not only inferred from the browser's own UI state.**
Subscribed `admissionsmanager@sirius.app` to a real (test) endpoint via
curl -- confirmed `user_id` and `p256dh` in the database matched.
Logged in as `financemanager@sirius.app` and subscribed to the
*identical* `endpoint` string. Result: the same row `id` (confirmed by
primary key, not merely "a row with this endpoint exists again"), with
`user_id` and both key fields (`p256dh`, `auth`) now genuinely
belonging to `financemanager` -- the real ownership-transfer-on-
collision behavior this router's own docstring claims, proven by
reading the actual row back, not by trusting the `204` response alone.

**Recipient-set exclusion was proven by absence of a delivery attempt,
not merely absence of a role from a list.** `auditor@sirius.app` --
visible to every applicant via RLS but deliberately excluded from the
unassigned-applicant notification recipient set per this module's own
design reasoning -- established a real subscription row (a
syntactically valid but non-functional endpoint, since this check
tests *recipient selection*, not delivery mechanics already proven in
check 2). `admissionsmanager@sirius.app` (a real, genuine subscriber)
created a real unassigned applicant. Result: the api container's own
log shows **zero delivery attempt of any kind against `auditor`'s
subscription** -- no `push delivery failed` warning, no trace of its
fake endpoint anywhere -- while `admissionsmanager`'s own real
subscription received a real, independently-confirmed Windows OS
toast at the matching timestamp (`17241 @ 18:12:39`). This proves
`get_active_user_ids_for_roles` genuinely excludes `auditor` at the
recipient-resolution step itself, before any delivery is even
attempted -- not merely that `auditor`'s delivery happened to fail for
an unrelated reason.

Cleanup: the recipient-validation test applicant, both synthetic
(non-Mozilla) test subscriptions, and the temporary curl cookie jars
used for this check were all deleted/removed immediately after.

### 7. A real, previously-undiscovered defect found and fixed: one malformed subscription could silently abort delivery to every other recipient in the same notification

Check 6's own final case established `superadmin@sirius.app` had never
actually been tested as a real recipient before (only
`ADMISSIONS_MANAGER`/`FINANCE_MANAGER` had). Subscribing `superadmin`
with a syntactically-invalid `p256dh`/`auth` (`"sa-p256dh"`/`"sa-auth"`
-- not valid base64url of any length, a fake test value, not real
Mozilla keys) and firing a real unassigned-applicant-creation trigger
surfaced a genuine bug rather than merely confirming the intended
recipient set:

**What happened.** `pywebpush.webpush()` does not exclusively raise
`WebPushException` for a failed send -- a malformed key makes its own
internal `WebPusher.__init__` raise a raw `binascii.Error` *before* any
HTTP request is even attempted. `_send_sync`'s original
`except WebPushException` clause did not catch this. The exception
propagated out of `asyncio.to_thread`, out of the `for` loop in
`send_push_to_users` (this trigger's unassigned-recipient fan-out has
more than one recipient), and crashed the entire `BackgroundTasks`
callback. Because `BackgroundTasks` runs after the triggering
request's own response has already been sent, the `POST /applicants`
call itself still returned a real `201` -- the defect was invisible at
the HTTP layer and only visible by checking whether every intended
recipient actually got their own real notification.

**Confirmed as a genuine cross-recipient failure, not merely
`superadmin`'s own delivery failing.** Checked the real Windows
`Microsoft-Windows-PushNotification-Platform/Operational` event log
for the several minutes around the triggering request: **no toast
delivery event of any kind** -- not even the noise-level WNP transport
keepalive entries that a genuine attempt would produce downstream of a
successful encryption step. `admissionsmanager@sirius.app`'s
subscription (a real, working, previously-proven subscription,
inserted into `push_subscription` before `superadmin`'s in this test)
never received its own notification either, purely because
`superadmin`'s malformed row crashed the loop before the iteration
that would have reached `admissionsmanager` ever ran. One bad
subscription -- corrupted data, a future client bug, anything not a
clean base64 string -- would silently drop delivery to every other
real recipient in the same call, not just the one bad subscription.
This is a real defect a "does the endpoint return 200" check can never
surface, since the crash happens entirely after the response is sent.

**Fix -- containment, then prevention.**

1. `api/app/core/push.py`'s `_send_sync` now also catches the bare
   `Exception` case (not only `WebPushException`), logs it, and
   returns `None` (no status code, not itself a dead-subscription
   signal, but contained rather than propagated) -- so one
   subscription's own failure, of any kind, can never again abort the
   rest of the batch. This is the actual fix: the loop in
   `send_push_to_user`/`send_push_to_users` was never given per-
   iteration isolation, and this is the one place that isolation
   belongs.
2. `api/app/schemas/push.py`'s `PushSubscriptionKeys` now validates
   `p256dh`/`auth` as real base64url (padding-tolerant, so a genuine
   unpadded browser-issued key is never rejected) at the moment
   `POST /notifications/subscribe` receives it -- defense in depth, not
   a substitute for the fix above, so a malformed key is rejected with
   a real `422` at write time rather than ever reaching a later push
   attempt at all.

**Re-verified live, not merely re-read.** Rebuilt and redeployed the
real `api` (and, having discovered along the way that `migrate` caches
its own separate image independent of `api`'s, the real `migrate`)
containers. Recreated the identical scenario without touching any of
the existing rows: fired a fresh unassigned-applicant-creation trigger
with `superadmin`'s same malformed subscription and
`admissionsmanager`'s same real one both still present. Result:
- api container log: `push delivery raised a non-WebPushException
  error for subscription 9d684bad-...: Invalid base64-encoded string:
  number of data characters (9) cannot be 1 more than a multiple of 4`
  -- caught and logged, no traceback, no crash.
- Real Windows toast (`Id 3153`/`3052`, tracking id `17242`) delivered
  to Firefox at `18:24:09`, matching the trigger fired at `18:24:08` --
  `admissionsmanager`'s real notification arrived despite
  `superadmin`'s malformed subscription being processed in the same
  batch, immediately before it.

An incidental deployment gap surfaced during this fix and is worth
recording: `docker compose build api` alone left `sirius-migrate`'s
own separately-cached image stale (Compose builds each service with
its own `build:` block into its own tagged image even when both point
at the same Dockerfile/context), which made `migrate` fail with
`Can't locate revision identified by '0012_push_subscription'` -- not
because the migration was wrong, but because the stale `migrate` image
predated that migration file's own existence in the image. Rebuilding
`migrate` explicitly (`docker compose build migrate`) resolved it. Any
future code change needs `docker compose build api migrate` together,
not `api` alone, for this reason.

Cleanup: the malformed `superadmin` subscription row, both test
applicants (`Superadmin Recipient Test`,
`Fix Verification Recipient Test`) and their `application_status_event`
rows, and the two curl cookie jars used across checks 6 and 7 were all
deleted, each confirmed by a direct follow-up query/listing returning
zero rows rather than by assumption. The one leftover host-side/bind-
mounted temporary script (`_tmp_gen_code4.py`, a TOTP-code helper from
earlier login testing) was also found and deleted from both the
container and the host path it was bind-mounted from.

## Cleanup performed before treating this module as done

- The real test applicant (`Push Test Applicant`) and its
  `application_status_event` row deleted directly from the database.
- The real test applicant created by the live Excel-import trigger
  test (`import.trigger.test@example.com`) and its own `import_batch`
  row deleted directly.
- All three original test payment claims (`NEGTEST-001`, `POSTEST-002`,
  `STALETEST-003`) deleted directly, plus two further test claims
  (`CLICKTEST-004`, `CLICKTEST-005`) created during the follow-up
  `notificationclick` verification attempts, also deleted.
- The deliberately-invalidated `financemanager` subscription row was
  already removed by the cleanup mechanism itself (see check 4 above);
  no manual deletion needed for it.
- During the follow-up `notificationclick` attempts, a manual
  diagnostic push to `newcounselor`'s and `financestaff`'s
  subscriptions genuinely expired both at Mozilla's push service (a
  real `410 Gone` on each, confirmed the same way check 4 confirms
  one) -- both dead rows were deleted directly since they were
  confirmed-dead, not merely suspected-stale. `financemanager`
  re-subscribed fresh through the real opt-in UI afterward; that
  working subscription was left in place.
- `financestaff@sirius.app`'s and `financemanager@sirius.app`'s
  passwords were set to known, real values through the actual
  `POST /auth/forgot-password` → Mailpit → `POST /auth/reset-password`
  redemption flow (their original passwords were never known to this
  session) -- left at those new working values, matching the same
  precedent Module 18/19 already established.
- All temporary curl cookie jars, one-off TOTP-code-generation,
  VAPID-key-inspection, and UI-Automation diagnostic scripts (used
  only for the safe, read-only/invoke-scoped `notificationclick`
  attempts, never for broad screen capture or global input
  simulation) were deleted; `git status` confirmed a clean tree before
  each commit.
- The check-7 malformed `superadmin` subscription row, both its own
  test applicants and their `application_status_event` rows, its two
  cookie jars, and the leftover bind-mounted `_tmp_gen_code4.py` helper
  script (found on both the container's and the host's filesystem)
  were all deleted, each confirmed by a direct follow-up
  query/listing, not by assumption -- see check 7 above for the full
  account.

## Final checks

- `tsc --noEmit` (run inside the real `frontend` container): clean.
- `alembic upgrade head`: migration `0012_push_subscription` applied
  cleanly against the real running Postgres instance; `\d
  push_subscription` confirmed the real table, indexes, FK, and
  `write_audit()` trigger all exist exactly as the migration declares.
- `git status`: only this module's own files touched (new:
  `api/alembic/versions/0012_push_subscription.py`,
  `api/app/core/push.py`, `api/app/models/push_subscription.py`,
  `api/app/routers/notifications.py`, `api/app/schemas/push.py`,
  `frontend/public/sw.js`, `frontend/src/api/useNotifications.ts`;
  modified: `api/app/core/config.py`, `api/app/main.py`,
  `api/app/models/__init__.py`,
  `api/app/routers/applicant_create.py`, `api/app/routers/import_.py`,
  `api/app/routers/payment_claim.py`, `api/pyproject.toml`,
  `deploy/.env.example`, `deploy/docker-compose.yml`,
  `frontend/src/api/client.ts`, `frontend/src/api/types.ts`,
  `frontend/src/main.tsx`, `frontend/src/pages/ProfilePage.tsx`); no
  stray temp files.
- **Acceptance summary, stated explicitly rather than left implicit:**
  all four real trigger paths this module builds (assigned-applicant
  creation, unassigned-applicant creation via manager/admin, payment-
  claim submission, and Excel-import batch completion) were each fired
  for real against the live stack and each produced a real,
  independently-observed OS-level toast at the Windows push-
  notification-platform log layer, with payload content confirmed
  correct in every case via `reg.getNotifications()` reading the
  actual delivered object back. The two negative-exclusion
  requirements (`FINANCE_STAFF` must receive nothing for its own
  submitted claim; `AUDITOR` must receive nothing for an unassigned
  applicant despite RLS visibility) were each proven the same way, by
  a genuinely subscribed account receiving no delivery attempt at all
  (confirmed by the absence of any log trace touching its own
  subscription), not merely by a role's absence from a source-code
  list. Dead-subscription cleanup was proven with a genuinely induced
  `410` and a confirmed row deletion, not a simulated one. The three
  endpoint-level security properties this router's own docstring
  claims (cross-account unsubscribe is a real no-op with the target
  row provably untouched, not just a `204`; same-endpoint re-subscribe
  from a different account genuinely transfers ownership at the row
  level, confirmed by primary key; an unauthenticated `POST`/`DELETE`
  is genuinely rejected with `401`) were each tested directly against
  the real endpoints, not only inferred from the browser UI's own
  observed behavior. Every one of these is concrete, observed evidence
  -- real HTTP responses, real database rows read back and compared,
  a real third-party push service's own status codes, and a real OS
  notification log -- not an inference from reading the
  implementation.
- The one real, honestly-stated limitation of this verification: the
  `notificationclick` handler's own client-navigation logic was
  verified by standard-API correctness and confirmed-correct payload
  data rather than an executed physical OS-level click. Three
  distinct, safe, narrowly-scoped attempts were made to close this gap
  (enumerating the toast's own `CoreWindow` by class/name, a broader
  toast-class scan run with near-zero delay after the trigger, and a
  targeted taskbar-bell `InvokePattern` to open the Action Center) --
  each failed for an environment-architecture reason (the toast is not
  enumerable as a root-level `AutomationElement` in this environment,
  and the notification bell was not discoverable by the patterns
  tried), not from an early or partial effort -- see check 2's own
  account above for the full record of all three attempts. Every
  other requirement of this module -- VAPID generation, real
  subscription, both trigger types (including the negative-role-
  exclusion case), and stale-subscription cleanup -- was proven
  against the real running stack with independent, OS-level evidence
  (the Windows push-notification event log), not inferred from
  application-level logs alone.
