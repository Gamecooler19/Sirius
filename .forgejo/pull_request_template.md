## What does this change?

<!-- Describe the change and why it's needed. -->

## Scope

<!-- What is in scope for this change? What is explicitly deferred? -->

## Live verification

<!--
Per CONTRIBUTING.md, this project verifies against the real running stack,
not code review alone. Describe what you actually ran and observed:
- Real psql connections through PgBouncer as the ordinary `sirius` role
  (never the bootstrap superuser), if this touches RLS or schema.
- Real HTTP requests against the running `api` container, or a real
  browser session against the real dev server, not a mocked backend.
- Any real defect this verification found and how it was fixed.
-->

## Checklist

- [ ] No secrets, TOTP codes, backup codes, or real credentials are included
      in this diff or its description.
- [ ] `deploy/.env` and `deploy/pgbouncer/userlist.txt` are not modified in
      a way that would be committed (both are gitignored).
- [ ] Any temporary helper script or scratch fixture used during
      verification has been deleted from both the container and the host.
- [ ] If this is a new module or a schema/RLS change, `reports/` and/or
      `docs/adr/` has been updated accordingly.
