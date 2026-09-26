# Product

## Register

product

## Users

Six distinct staff roles at Illinois Tech Mumbai's admissions and finance
office, using this daily as an internal operational tool, not a public-facing
product: `SUPER_ADMIN`, `ADMISSIONS_MANAGER`, `ADMISSIONS_COUNSELOR`,
`FINANCE_STAFF`, `FINANCE_MANAGER`, `AUDITOR`. They are in a task — moving an
applicant through a fixed pipeline, reconciling a payment claim, running an
Excel import — not browsing. Context is a desk, a real monitor, working
hours, low ambient distraction, high trust in the tool because money and
admissions decisions ride on it.

## Product Purpose

Replace two disconnected spreadsheets (one admissions, one finance) with one
shared system where every applicant's admissions status and finance balance
live together, every payment claim requires a second person's confirmation
before it counts (maker-checker), every mutation is attributable in an
append-only audit trail, and role-based visibility is enforced twice — once
in application code, once again in PostgreSQL row-level security as
defense-in-depth. Success looks like: a counselor never sees finance data, a
finance staff member can submit a claim but never resolve their own, and an
auditor can review everything without being able to change anything.

## Brand Personality

Three words: **precise, accountable, unhurried.** This is not a startup
dashboard performing energy it doesn't have — it's closer to the register at
a bank branch or a university bursar's office: correct, calm, and quietly
serious about getting the numbers right. The tool should feel like it has
been doing this exact job for years, not like it launched last week.

Named reference: Linear's information density and restraint (one considered
accent color, not a rainbow of category tags) — but *not* Linear's
after-dark, command-palette-forward energy. This tool lives in daylight, on
a desk, during business hours.

## Anti-references

- Not a SaaS marketing site wearing a dashboard costume — no hero sections,
  no gradient-text metrics, no "delightful" onboarding confetti.
- Not the AI-purple/violet default. Not Mantine's own stock default blue
  either — v1 of this redesign already fell into "barely-styled defaults
  with a teal swapped in," which is the specific failure this pass exists
  to correct.
- Not warm-cream/beige-on-everything (the 2026 AI default surface).
- Not glassmorphism, not neumorphism, not decorative card grids for their
  own sake — every card must earn its elevation.

## Design Principles

1. **Earned familiarity, not novelty.** The bar is: would someone fluent in
   Linear, Stripe's dashboard, or a real university ERP sit down and trust
   this immediately, or pause at something subtly off. Never invent a
   custom affordance where a standard one already works.
2. **The accent is scarce and load-bearing.** One brand color, used for
   primary actions, current selection, and links — never decoration. It
   must never be confusable with the app's own semantic status colors
   (applicant pipeline stages, payment-claim statuses).
3. **Empty states teach, they don't apologize.** Several screens are
   legitimately empty right now (a fresh reset, or a page whose data
   arrives in a later module). An empty state is a real design moment, not
   dimmed placeholder text in a void.
4. **Nothing here changes what the system does.** Every role gate,
   RLS-scoped query, and maker-checker control (who may submit a payment
   claim vs. who may resolve one, who may run an import vs. who may only
   view its history) stays byte-identical in behavior through this
   redesign. A visual pass changes how things look, never what they show
   or allow.
5. **Density serves the task.** This is a real admin tool with real tables
   of real rows. Whitespace is used to establish rhythm and hierarchy, not
   to make the tool feel like a marketing page — a dense, well-typeset
   table beats an airy one that requires more scrolling to do the same
   job.

## Accessibility & Inclusion

WCAG AA minimum across the whole surface: body text ≥4.5:1 against its
background, large text/UI components ≥3:1. `prefers-reduced-motion` honored
on every transition. The three roles with the most sensitive access already
require mandatory TOTP two-factor at the application layer; the visual layer
must never weaken that by, for example, making a disabled/blocked action
look identical to an enabled one.
