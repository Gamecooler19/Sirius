# Module 12: Docker frontend, git reconciliation, and visual redesign — completion report

## Scope

Three sequential phases, each gated on the previous one being confirmed working before starting the next: (1) diagnose and fix this repository's git remote/branch state — add a `github` remote alongside the existing `origin` (Forgejo), reconcile a `master`/`main` duplication on Forgejo itself, and confirm an identical end state across local, Forgejo, and GitHub; (2) add the frontend to the Docker Compose stack as its own service running Vite's dev server directly (no reverse proxy), and verify a real login still works end to end through the containerized frontend; (3) a visual redesign pass using this environment's design skills, explicitly scoped to *how the app looks*, never *what it's allowed to do or show* — verified with a real login/navigate/act smoke test across two different roles afterward.

## Part 1 — Git diagnosis and reconciliation

### Diagnosis (before any change)

`git remote -v` showed only `origin` → `https://git.vrip7.com/gamecooler19/Sirius.git`, no `github` remote. `git branch -a` showed the local repository already on branch `main` (a prior session had renamed `master` → `main` locally, per `git reflog`), with `remotes/origin/HEAD -> origin/master` still stale and both `remotes/origin/main` and `remotes/origin/master` present.

Querying the Forgejo API directly (`GET /api/v1/repos/gamecooler19/Sirius/branches`) confirmed the real remote state: both `main` and `master` existed on `git.vrip7.com`, and **both pointed at the identical commit** `0363b527122a63192f16ca648ca7172fbec4bb7c` — not diverged. `GET /api/v1/repos/gamecooler19/Sirius` additionally showed `default_branch: "master"` still active. This matched the task's stated expectation exactly, so no ambiguity to report before acting.

### GitHub remote and push

Added a second remote, correctly named `github` (not `origin`, which already correctly points at Forgejo): `git remote add github https://github.com/Gamecooler19/Sirius.git`.

`git push -u github main` succeeded without any credential prompt — the existing Git Credential Manager already held valid `github.com` credentials on this machine (no token was hunted for in any file, per this project's own credential-hygiene rule). Verified via GitHub's own API (`GET /repos/Gamecooler19/Sirius/branches/main`): the pushed commit SHA matches `0363b527122a63192f16ca648ca7172fbec4bb7c` exactly, and the repository's `default_branch` is already `main` (GitHub's own default for a repo created without an initial commit on `master`).

### Forgejo reconciliation

Since `master` and `main` pointed at the identical commit, deleted the now-redundant `master` and set `main` as the single default branch. The Forgejo API's own `PATCH /repos/{owner}/{repo}` endpoint requires `admin` permission on the repository (`"permissions":{"admin":false,"push":false,...}` for the currently-authenticated read via unauthenticated API token), which the ambient read-only API access this session had did not carry — so the default-branch change was made through Forgejo's own web UI (`/gamecooler19/Sirius/settings/branches`) in an already-authenticated browser session (the same session used for Module 11's Forgejo template verification), driving the real Fomantic UI dropdown and submitting the real form rather than guessing at an unauthenticated API call. Confirmed the change landed by re-querying the *unauthenticated* API afterward: `default_branch: "main"`, `updated_at` freshly bumped to the moment of the change.

`git push origin --delete master` then removed the redundant branch. Re-queried `GET /api/v1/repos/gamecooler19/Sirius/branches` afterward: only `main` remains.

### End-state confirmation

| | Local | Forgejo (`origin`) | GitHub (`github`) |
|---|---|---|---|
| Branches | `main` only | `main` only | `main` only |
| HEAD SHA | `0363b527...` | `0363b527...` | `0363b527...` |
| Default branch | n/a | `main` | `main` |

All three verified independently — `git rev-parse HEAD` locally, `git ls-remote origin`, `git ls-remote github`, and the GitHub/Forgejo REST APIs directly, not inferred from `git push`'s own exit code alone.

## Part 2 — Frontend containerization

### What was added

`frontend/Dockerfile`: a plain `node:22-alpine` image running `npm run dev` (Vite's own dev server) directly as the container's `CMD` — no build step, no `nginx`/`Caddy`/any reverse proxy, matching the explicit instruction. `frontend/.dockerignore` excludes `node_modules`/`dist`/`.env*` from the build context.

`deploy/docker-compose.yml` gained a `frontend` service:
- Published on `127.0.0.1:5173:5173` — the same loopback-only convention every other host-published service (`api`, `rustfs`) already uses, not `0.0.0.0`.
- Bind-mounts the real `../frontend` source tree into `/app`, with an anonymous volume over `/app/node_modules` so the container's own Linux-native `npm ci` install is never shadowed by the host's Windows-native `node_modules` — hot-reload against real host edits keeps working, matching the live-editing workflow Modules 06–10 already had running the dev server directly on the host, rather than regressing to an image-rebuild-per-edit loop.
- `CHOKIDAR_USEPOLLING=true` so Vite's file watcher works reliably across the bind-mount boundary.
- `depends_on: api: condition: service_healthy`.

### CORS_ORIGINS

No change was needed. `deploy/.env`'s existing `CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173` (set in Module 06, carried through Module 11's secret regeneration) already matches exactly where the containerized frontend now serves from — the container publishes on the identical host loopback port `5173` the host-run dev server previously used. This was verified live, not assumed from the port number matching: a real browser login against `http://127.0.0.1:5173` (below) succeeded on the first attempt with no CORS error, confirming the existing `CORS_ORIGINS` value was already correct for the new container.

### Live verification

`docker compose up -d --build frontend` built and started the container; `docker compose logs frontend` showed a clean Vite startup (`VITE v8.3.1 ready in 317 ms`) bound to `0.0.0.0:5173` inside the container (via `vite.config.ts`'s pre-existing `server.host = true`), reachable at `http://127.0.0.1:5173` on the host. `curl http://127.0.0.1:5173/` returned `200`.

A real login was driven through a real Firefox browser session against this containerized frontend, not merely confirming the container started:
1. Opened `http://127.0.0.1:5173/login` — real page load, correct Sirius branding.
2. Filled real credentials for `admissionsmanager@sirius.app` and clicked the real "Sign in" button.
3. Browser navigated to `http://127.0.0.1:5173/` — the authenticated shell rendered with the correct role-gated nav for `ADMISSIONS_MANAGER` (Home, Applicants, Import applicants, Import history — no Finance/Reconciliation, matching `roles.ts`).
4. Navigated to `/applicants` — a real `GET /applicants` request through the container reached the real `api` container and returned a real (empty, correctly post-Module-11-reset) result set, rendered as "No applicants match these filters. / 0 results" — the correct empty state, not a 404 or CORS failure.

This confirms the full chain end to end: browser → containerized Vite dev server → containerized FastAPI `api` (via the browser's own direct cross-origin request, not proxied through the frontend container) → PgBouncer → Postgres, with the httpOnly session cookie correctly set and sent on the follow-up request.

## Part 3 — Visual redesign

### Design skills available

Checked all five named skills; all were available in this environment and were read before writing any component:
- `emil-design-eng` — animation/motion philosophy (easing curves, durations, GPU-only properties, tactile press feedback).
- `review-animations` — the review-side counterpart; used as a self-check checklist against the motion changes made.
- `design-taste-frontend` — read, but explicitly out of scope by its own Section 13 ("NOT for... dashboards / dense product UI / admin panels"); Sirius is exactly that category, so this skill's landing-page-specific rules (hero copy limits, marquees, bento grids) were not applied.
- `redesign-existing-projects` — the primary skill applied: audit-first, work with the existing stack (Mantine + Tailwind v4), targeted fixes over a rewrite.
- `impeccable` — checked for its own project-scaffolding requirement (`.pi/skills/impeccable/scripts/context.mjs`); this project has no `.pi/` directory, so its automated setup flow doesn't apply here. Its written design guidance (contrast verification, motion rules, ban list) was still applied manually where it overlapped with `redesign-existing-projects` and `emil-design-eng`.

### Audit (before any change)

`App.tsx`'s `<MantineProvider>` had zero customization — Mantine's stock default blue primary color, default border radii, and the browser's default system font stack, indistinguishable from a fresh `npx mantine` scaffold. This is the generic-UI problem both design skills flag as the highest-priority fix (`redesign-existing-projects`' own "Fix Priority" list puts font swap and color-palette cleanup first).

### What changed

**Typography.** Self-hosted Geist (body/display) and Geist Mono (tabular data: money, IDs, timestamps) via `@font-face` in a new `src/fonts.css`, per the redesign skill's explicit rule ("self-host with `@font-face`, never link Google Fonts in production"). The variable-weight `.woff2` files were copied from the `geist` npm package (SIL Open Font License 1.1, redistribution explicitly permitted — checked the license text directly, not assumed) into `public/fonts/`, since `next/font`'s build-time font loading has no equivalent in a plain Vite app; this is the correct non-Next.js substitute, not a shortcut around the rule.

**Color.** A new `src/theme.ts` defines a single deliberate teal/cyan accent (`sirius`), replacing Mantine's default blue. The shade was picked by actually computing WCAG contrast ratios for every shade in the 10-step color tuple against white text (Mantine's default filled-button text color) rather than eyeballing it — the first choice (shade index 5, the visually "brightest" teal) only reached 2.12:1 contrast, a real accessibility failure per the redesign skill's mandatory "Button Contrast Check." Shade index 7 (5.21:1) was used instead, passing WCAG AA's 4.5:1 threshold. The accent was also chosen deliberately to sit apart from every semantic status color already in use (`STATUS_COLORS` in `ApplicantsPage`/`FinancePage`: gray/blue/yellow/orange/grape/green/red/dark) so the brand accent can never be mistaken for a status badge.

**Shape and shadow consistency.** One radius scale (`xs` 4px through `xl` 16px) applied via `theme.radius`, replacing per-component ad hoc radii — the redesign skill's "Shape Consistency Lock." Shadows tinted toward the brand hue (`rgba(6, 60, 55, ...)`) rather than pure black, per the same skill's shadow-tinting rule.

**Motion.** Global CSS rules in `index.css`, each individually justified against Emil Kowalski's framework rather than added by default:
- Buttons/action-icons get a `scale(0.97)` `:active` state (140ms, a real cubic-bezier ease-out, not the weak built-in CSS `ease-out`) — Emil's "buttons must feel responsive to press" rule. This is a tens-of-times-a-day interaction for this app, well within the "standard animation" band, not the "never animate" band reserved for 100+/day or keyboard-triggered actions.
- Table row hover: background-color transition only, no transform — a dense data table's rows visibly shifting on hover would read as jittery, not polished.
- `NavLink` active/hover: background/color transition, same reasoning.
- The `ApplicantDetailDrawer`'s open/close transition was given an explicit `transitionProps` (220ms, the same ease-out curve) instead of Mantine's untuned default — sits correctly in Emil's 200–500ms band for drawers/modals.
- Every rule above animates only `transform`/`opacity`/`background-color` (GPU-composited, per the performance rules both `emil-design-eng` and `redesign-existing-projects` require), stays under 300ms, and is wrapped in `@media (prefers-reduced-motion: reduce)` with transforms dropped and only opacity/color transitions retained — the mandatory accessibility requirement neither skill treats as optional.

**Numeric alignment.** `font-variant-numeric: tabular-nums` set globally, plus the existing `ff="monospace"` usage in `FinancePage`/`ImportUploadPage` now resolving to the self-hosted Geist Mono instead of a generic system monospace fallback — addresses the redesign skill's "Numbers in proportional font" fix for money/ID columns.

### What was deliberately not changed

No component's data-fetching hook, role-gate check (`hasRole`, `canUpload`, `canResolve`, `canTransition`), RLS-scoped query, or maker-checker control was touched. `design-taste-frontend`'s marketing-page-specific rules (hero word limits, eyebrow rationing, marquee caps, bento cell counts) do not apply to this app's register and were not applied. No new component library, animation library, or icon set was introduced — Mantine, Tailwind v4, and Phosphor Icons (the existing stack) were reused throughout, per the redesign skill's "work with the existing tech stack, do not migrate frameworks" rule.

### Behavioral smoke test after the redesign

Driven live against the containerized frontend, across two different roles, confirming every role gate, RLS-scoped view, and maker-checker control still behaves identically to before the redesign:

**`ADMISSIONS_MANAGER`** (`admissionsmanager@sirius.app`): logged in, landed on the authenticated shell, correct nav (Home/Applicants/Import applicants/Import history — no Finance/Reconciliation, matching `APPLICANTS_ROLES`/`FINANCE_ROLES` in `roles.ts`), navigated to `/applicants` and `/import`, both rendered their real empty states correctly with the new theme applied.

**`AUDITOR`** (`auditor@sirius.app`): logged in, correct nav (Home/Finance/Reconciliation/Import history — no Applicants, no Import applicants link, matching the auditor's real role membership), navigated to `/finance` and confirmed the payment-claims table renders **no "Actions" column at all** (the auditor is not in `PAYMENT_RESOLVE_ROLES`) — the exact maker-checker UI behavior Module 09 established, unaffected by the visual pass. Navigated directly to `http://127.0.0.1:5173/import` by URL (bypassing the nav, which correctly omits this link for an auditor) and confirmed the page still renders "Your role cannot run an applicant import." — the role gate holds even via a direct URL, not merely by hiding the nav link. Navigated to `/import/history` (which the auditor *can* see) and confirmed its real empty state renders correctly.

`npx tsc -b --noEmit` (run inside the container) and `npm run lint` (oxlint) both passed with zero errors after every change. `npm run build` (the production Vite build, run inside the container) succeeded, producing a real bundle — confirming the redesign is compatible with the production build path even though local development runs the dev server directly, per the containerization requirement.

## Cleanup

The throwaway `_template-check` branch created during Module 11's own Forgejo-template live-verification follow-up (see this session's earlier work) was already deleted from both the remote and local repository before this module began; `git branch -a` and `git ls-remote origin` at the start of Part 1 confirmed only `main`/`master` existed, no stray branches. No temporary scripts, scratch files, or debug artifacts were created during this module beyond the two intentionally-transient files already covered above (a contrast-ratio checker script, deleted immediately after use).
