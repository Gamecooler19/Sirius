---
name: Sirius
description: Admissions and finance tracker for Illinois Tech Mumbai — precise, accountable, unhurried.
colors:
  primary: "#005681"
  primary-hover: "#004573"
  primary-active: "#003a5f"
  primary-subtle-bg: "#e5f3fa"
  accent-amber: "#a75d00"
  accent-amber-chip-bg: "#feebd6"
  accent-amber-chip-text: "#6c3a00"
  bg: "#ffffff"
  surface: "#f3f8fa"
  surface-2: "#ebf1f4"
  ink: "#0c181d"
  muted: "#58666d"
  border: "#d9dfe2"
  border-strong: "#b9c4c9"
  danger: "#b3261e"
  danger-subtle-bg: "#fceceb"
  success: "#1e6b3c"
  success-subtle-bg: "#e8f5ec"
typography:
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "normal"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  mono:
    fontFamily: "ui-monospace, SFMono-Regular, 'Segoe UI Mono', Consolas, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
rounded:
  sm: "6px"
  md: "8px"
  lg: "12px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "40px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-primary-active:
    backgroundColor: "{colors.primary-active}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  input-field:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  nav-item-active:
    backgroundColor: "{colors.primary-subtle-bg}"
    textColor: "{colors.primary}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
---

# Design System: Sirius

## 1. Overview

**Creative North Star: "The Harbor Master's Ledger"**

Sirius runs like the office of a harbor master at dawn: cold steel water,
fog-muted light, the quiet before the boats leave. Every entry in the
ledger is checked twice, every signature is attributable, and nothing is
decorative — the room exists to get the count right, not to impress a
visitor. The deep cobalt of pre-dawn water is the only color the interface
volunteers on its own; everything else is neutral until a real state
(a status, an error, a selection) earns it.

This system explicitly rejects the SaaS-marketing-dashboard costume: no
hero sections, no gradient-text metrics, no confetti on save. It also
rejects the two failure modes of the redesign that preceded it — Mantine's
stock default blue with a teal accent swapped in, and, before that,
completely unstyled defaults. Sirius is closer to a bank branch's teller
system or a university bursar's ledger than to a startup dashboard: it has
been doing this exact job for years and it shows in the confidence of the
restraint, not in visual noise.

**Key Characteristics:**
- One brand color (deep cobalt), used sparingly and only where it means
  something — primary actions, current navigation, links, focus rings.
- A dense, tabular-numeral, fixed-rem type scale built for real data, not
  a fluid marketing scale.
- Flat by default; elevation appears only where it communicates real
  hierarchy (the navigation drawer over content, a modal over the page).
- Semantic status colors (applicant pipeline stages, payment-claim states)
  are a *separate* vocabulary from the one brand accent, so the two never
  collide or get mistaken for each other.

## 2. Colors

A cold, considered palette: one deep cobalt primary, one warm amber accent
held in reserve for a single distinct role, and a cool-tinted neutral ramp
that never drifts into the 2026 AI-default cream.

### Primary
- **Harbor Cobalt** (#005681): the single brand color. Primary buttons,
  active navigation, links, focus rings, the current selection. Used
  sparingly — this is not a "committed" palette where color carries a
  third of the surface; it is Restrained, per the product register's own
  default. Text on Harbor Cobalt is always white (7.93:1 contrast).
- **Harbor Cobalt, Hover** (#004573): 10.01:1 against white text, one step
  darker for the pressed/hover state of anything filled with Primary.
- **Harbor Cobalt, Active** (#003a5f): the pressed state, one step darker
  still.
- **Harbor Cobalt, Subtle** (#e5f3fa): the tint used for the active
  navigation item's background and any "currently selected" chip — never
  for large surfaces.

### Secondary — Fog Amber
- **Fog Amber** (#a75d00): the one deliberate second hue, reserved
  exclusively for the "flagged / needs attention" register — a flagged
  import row, a note requiring review. It is never used for a primary
  action; the two colors must never compete for the same job.
- **Fog Amber, Chip** (background #feebd6, text #6c3a00, 8.06:1 contrast):
  the pill treatment for the amber role — always this exact pairing, never
  a solid amber fill with white text on a small chip.

### Neutral
- **Deep Harbor Ink** (#0c181d): body text, headings. 18.04:1 against the
  white surface — deliberately higher than the WCAG floor because dense
  tabular data is read for long stretches, not skimmed.
- **Fog Muted** (#58666d): secondary text, timestamps, helper copy.
  5.94:1 against white — passes the ≥3.5:1 floor with real margin.
- **Steel Surface** (#f3f8fa): the app shell's own background — sidebar,
  header — one step off pure white, cool-tinted toward the primary's own
  hue rather than warm.
- **Steel Surface, Deep** (#ebf1f4): hover state for list rows and nav
  items that aren't the active selection.
- **Fogline Border** (#d9dfe2): hairline dividers, table borders, input
  borders at rest.
- **Fogline Border, Strong** (#b9c4c9): input borders on focus-adjacent or
  emphasized dividers.

### Status vocabulary (separate from brand color)
- **Danger** (#b3261e on a #fceceb chip): rejected/failed states.
- **Success** (#1e6b3c on a #e8f5ec chip): confirmed/completed states.
- The existing applicant-pipeline and payment-claim status badges
  (gray/blue/yellow/orange/grape/green/red) are untouched by this palette
  — they are a distinct semantic system this redesign does not collapse
  into the brand color, by design (see Principle 2 in PRODUCT.md).

### Named Rules
**The One Signal Rule.** Harbor Cobalt appears exactly once per screen as
a rule of thumb: the single primary action, or the single active nav item,
or a focus ring — never as a background wash, never twice competing for
attention in the same view.

## 3. Typography

**Body Font:** the OS-native UI sans stack —
`-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif`. No
web font is loaded at all.
**Label/Mono Font:** the OS-native monospace stack —
`ui-monospace, SFMono-Regular, 'Segoe UI Mono', Consolas, monospace` — for
every tabular figure: money, IDs, timestamps, counts — so columns of
numbers actually align.

**Character:** One family, multiple weights — the product register's own
rule that dashboards don't need a display/body pairing, and per the
`impeccable` `typeset` reference itself: *"Product: system fonts and
familiar sans stacks are legitimate here. One well-tuned family typically
carries the whole UI."* This module's first pass self-hosted Geist, on the
theory that a distinctive face would read as more "designed" than a system
default. Running `impeccable detect` against the result flagged Geist
itself under `overused-font` — it has become common enough in 2025-26 AI
UI output to read as a tell in its own right, the same failure mode as
Inter before it. The fix is not a different distinctive face; it's
accepting the register's own guidance that a system stack is the correct,
undistracting choice for an instrument-panel tool a user stares at for
hours a day. San Francisco / Segoe UI disappear into "just text," which is
exactly this ledger's register — and it ships zero font bytes, so page
load and CLS both improve for free.

### Hierarchy
- **Headline** (700, 24px, 1.25 line-height, -0.015em tracking): page
  titles only ("Applicants", "Finance", "Reconciliation"). One per screen.
- **Title** (600, 18px, 1.3 line-height, -0.01em tracking): section
  headers within a page (a drawer's own heading, a card group title).
- **Label** (500, 13px, 1.4 line-height): form labels, table headers, nav
  items, button text.
- **Body** (400, 14px, 1.5 line-height): the default for everything else —
  table cell content, paragraph copy, drawer body text.
- **Mono** (400, 13px, system monospace stack, tabular numerals on by
  default): every money amount, ID, timestamp, and count.

### Named Rules
**The Fixed-Scale Rule.** No `clamp()`, no fluid viewport-based sizing
anywhere in this system. Users view a data-dense tool at a consistent
desktop DPI; a fluid headline that shrinks in a sidebar reads as broken,
not responsive. Every size above is a fixed `px` value; only layout
(sidebar collapse, table scroll) responds to viewport width.

## 4. Elevation

Sirius is flat by default and earns elevation only where it communicates
real hierarchy, not as decoration on every card. Two elevation contexts
exist: the persistent navigation surface sitting above the content plane,
and a transient overlay (the applicant-detail drawer) sitting above
everything.

### Shadow Vocabulary
- **Panel** (`box-shadow: 0 1px 0 0 #d9dfe2`): a single hairline border,
  not a shadow at all, separates the header/sidebar from the content
  plane. This is the default state for 95% of the interface.
- **Overlay** (`box-shadow: -8px 0 24px rgba(12, 24, 29, 0.10)`): the one
  real elevation in the system, used exclusively for the applicant-detail
  drawer sliding in over content. Tinted toward Deep Harbor Ink, not
  generic black.
- **Focus Ring** (`box-shadow: 0 0 0 2px #ffffff, 0 0 0 4px #005681`): a
  double ring (white gap + cobalt ring) on every keyboard-focusable
  element, visible against any surface underneath it.

### Named Rules
**The Earned Elevation Rule.** A card, panel, or shadow must justify its
existence by separating two things a user could otherwise confuse — the
nav from the content, an overlay from the page beneath it. A card wrapped
around content that would read identically without it is a Don't (see
§6): use a hairline divider or plain spacing instead.

## 5. Components

### Buttons
- **Shape:** 6px radius (sm) — sharper than a typical consumer app,
  matching the instrument-panel character; never pill-shaped.
- **Primary:** Harbor Cobalt fill (#005681), white text, `8px 16px`
  padding, Label typography. Hover → #004573, Active → #003a5f (scale
  0.97 on `:active` for tactile press feedback, 140ms ease-out).
- **Secondary:** Steel Surface fill (#f3f8fa), Deep Harbor Ink text, same
  shape and padding as Primary. Used for every non-primary action
  (Logout, Cancel, secondary filters).
- **Danger:** same shape, filled with Danger red, white text — reserved
  for destructive/rejecting actions only (Reject on a payment claim).

### Badges / Status Pills
- **Style:** existing semantic status vocabulary (per-status background
  tint + matching text color, no border, 6px radius) is preserved exactly
  as Modules 03–10 built it — this redesign does not touch status-badge
  color logic, only the type/spacing/radius system it renders inside.
- **Fog Amber chip:** the one new chip role this system adds, reserved for
  a "flagged" state, using the exact chip pairing from §2.

### Cards / Containers
- **Corner Style:** 12px radius (lg) — used only for the reconciliation
  summary tiles, where a card genuinely separates one metric from its
  neighbors on a dashboard-style grid. Not used as a wrapper around list
  rows, form sections, or anything a hairline divider already separates.
- **Background:** Steel Surface (#f3f8fa) on a white page, so the card
  reads as one step of elevation without a drop shadow.
- **Shadow Strategy:** none at rest; the background-color step against
  the page is the entire signal.
- **Border:** none — background contrast does the separating.
- **Internal Padding:** 24px (lg spacing token).

### Inputs / Fields
- **Style:** 1px Fogline Border (#d9dfe2), white background, 6px radius,
  `8px 12px` padding, Body typography.
- **Focus:** border shifts to Harbor Cobalt plus the double Focus Ring
  from §4 — never a glow-only treatment, always a visible ring for
  keyboard users.
- **Error:** border shifts to Danger red; error text appears below the
  field in Danger red, Label typography.
- **Disabled:** Steel Surface background, Fog Muted text, no border
  change on focus (disabled fields are never focusable).

### Navigation
- **Style:** left sidebar, Steel Surface background, persistent, no
  collapse-to-icons state on desktop.
- **Default item:** Deep Harbor Ink text, Label typography, transparent
  background.
- **Hover:** Steel Surface Deep (#ebf1f4) background.
- **Active:** Harbor Cobalt Subtle (#e5f3fa) background, Harbor Cobalt
  text — the one place "current selection" earns the brand color as a
  background tint, per the One Signal Rule.
- **Mobile treatment:** below 768px the sidebar becomes a slide-over
  drawer triggered by a burger control in the header, never a squeezed
  or icon-only sidebar — verified live at a real narrow viewport as part
  of this module's own responsive pass.

### Empty States (signature component)
Every list/table screen that can be legitimately empty (a fresh reset, or
a page whose data ships in a later module) gets a composed empty state,
not dimmed placeholder text: a Phosphor icon appropriate to the screen's
own subject (people for Applicants, currency for Finance, chart for
Reconciliation, upload/clock for the two Import pages) at 32px in Fog
Muted, a Title-weight headline naming what's missing, and one line of
Body-weight explanatory text — composed inside the same Steel Surface
card treatment as the reconciliation tiles, centered, with generous
padding (40px). This is the component this redesign pass exists to add;
v1 shipped bare "No X match these filters" text in a table row, which
read as unfinished.

## 6. Do's and Don'ts

### Do:
- **Do** use Harbor Cobalt (#005681) exactly once per screen as the
  single primary signal — a button, an active nav item, a focus ring.
- **Do** render every money/ID/timestamp/count in the system monospace
  stack with tabular numerals so columns of numbers align.
- **Do** compose a real empty state (icon + headline + one line of body
  text, inside a Steel Surface card) for every screen that can be
  legitimately empty, per PRODUCT.md's "Empty states teach, they don't
  apologize" principle.
- **Do** keep the existing semantic status-badge vocabulary
  (gray/blue/yellow/orange/grape/green/red for applicant/payment-claim
  states) completely separate from the one brand accent.
- **Do** verify every role gate, RLS-scoped view, and maker-checker
  control renders identically in behavior before and after this pass —
  per PRODUCT.md Principle 4, this is non-negotiable.

### Don't:
- **Don't** use Mantine's stock default blue, or any "AI-purple" accent —
  the two failure modes this exact redesign exists to correct.
- **Don't** use a warm-cream/beige surface anywhere; the neutral ramp
  stays cool-tinted toward the primary's own cobalt hue.
- **Don't** wrap list rows, form sections, or anything a hairline divider
  already separates in a card — per the Earned Elevation Rule, a card
  must justify its own existence.
- **Don't** use `border-left`/`border-right` greater than 1px as a colored
  accent stripe on any element — rewrite with a background tint or a
  leading icon instead.
- **Don't** use `clamp()` or fluid viewport-based type sizing anywhere —
  per the Fixed-Scale Rule, this is a desktop data tool, not a marketing
  page.
- **Don't** ship a bare "No results" text row as an empty state — every
  empty state gets the full composed treatment from §5.
