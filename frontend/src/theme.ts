/**
 * Module 13 visual redesign (impeccable-only): Mantine theme overrides.
 * Replaces Module 12's teal palette entirely with the "Harbor Cobalt"
 * system computed via impeccable's own `palette.mjs --from
 * "sirius-v2-admissions-finance"` (seed: oklch(0.550 0.105 230deg)) and
 * documented in full, with every contrast ratio, in `DESIGN.md` at the
 * repo root -- this file is a direct application of that document, not an
 * independent design decision made in code.
 *
 * v1 (Module 12) chose teal specifically to sit apart from the app's
 * existing status-badge colors (gray/blue/yellow/orange/grape/green/red).
 * v2 keeps that same constraint -- Harbor Cobalt's hue (230deg, a
 * blue-leaning cobalt) reads as visually distinct from the badge "blue"
 * (Mantine's own `blue.6`, a brighter cyan-blue) at a glance, and DESIGN.md
 * Do's/Don'ts explicitly re-affirms the badge vocabulary is untouched.
 *
 * Font stack: after this module ran `impeccable detect` against v1's
 * self-hosted Geist and got a real `overused-font` finding (Geist itself
 * has become common enough in AI-generated UI to read as a tell), v2 uses
 * the OS-native system stack instead -- see DESIGN.md SS3 for the full
 * rationale and the `typeset.md` reference quote it's built on.
 */

import { createTheme, type MantineColorsTuple } from "@mantine/core";

// Harbor Cobalt: a 10-step OKLCH-derived tonal ramp at hue 230deg, computed
// from-scratch (Python OKLCH->linear-sRGB->gamma-encoded conversion,
// verified against DESIGN.md's own hand-checked primary/hover/active
// values) so shades 0-5 and 9 are a real perceptually-uniform ramp rather
// than an arbitrary CSS gradient; shades 6-8 are pinned to the exact hex
// values DESIGN.md already verified for WCAG contrast (7.93:1 / 10.01:1 /
// 12.1:1+ against white text) so the two documents can never drift apart.
const harborCobalt: MantineColorsTuple = [
  "#e7f6ff", // 0
  "#cbe6f4", // 1
  "#a0cbe1", // 2
  "#68a8c7", // 3
  "#2b85aa", // 4
  "#00658e", // 5
  "#005681", // 6 -- primary (DESIGN.md SS2), 7.93:1 white-text contrast
  "#004573", // 7 -- hover (DESIGN.md SS2), 10.01:1 white-text contrast
  "#003a5f", // 8 -- active (DESIGN.md SS2), 12.1:1+ white-text contrast
  "#001f3a", // 9 -- darkest
];

// Fog Amber: the one reserved secondary hue (DESIGN.md SS2), used only for
// the amber status chip -- never as a Mantine `color` prop on an
// interactive element, so this tuple exists solely so components that
// need the raw hex can reference `theme.colors["fog-amber"]` instead of a
// magic string.
const fogAmber: MantineColorsTuple = [
  "#fef3e2",
  "#feebd6", // 1 -- chip background (DESIGN.md SS2)
  "#f7d3a8",
  "#eeb877",
  "#e19b47",
  "#c47f22",
  "#a75d00", // 6 -- accent (DESIGN.md SS2)
  "#8a4d00",
  "#6c3a00", // 8 -- chip text (DESIGN.md SS2), 8.06:1 contrast on chip bg
  "#4a2700",
];

const SYSTEM_SANS =
  "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif";
const SYSTEM_MONO =
  "ui-monospace, SFMono-Regular, 'Segoe UI Mono', Consolas, monospace";

export const theme = createTheme({
  primaryColor: "harbor-cobalt",
  colors: { "harbor-cobalt": harborCobalt, "fog-amber": fogAmber },
  primaryShade: 6,

  fontFamily: SYSTEM_SANS,
  fontFamilyMonospace: SYSTEM_MONO,

  // DESIGN.md SS3 hierarchy: Headline/Title/Label/Body/Mono, fixed px
  // sizes, no fluid clamp() anywhere (the Fixed-Scale Rule).
  fontSizes: {
    xs: "0.8125rem", // 13px -- Label
    sm: "0.875rem", // 14px -- Body
    md: "0.875rem",
    lg: "1.125rem", // 18px -- Title
    xl: "1.5rem", // 24px -- Headline
  },

  headings: {
    fontFamily: SYSTEM_SANS,
    fontWeight: "600",
    sizes: {
      // h1 doubles as DESIGN.md's Headline role (24px/700/-0.015em); h2-h4
      // step down toward Title (18px/600/-0.01em) for in-page sub-sections.
      h1: {
        fontSize: "1.5rem",
        lineHeight: "1.25",
        fontWeight: "700",
      },
      h2: {
        fontSize: "1.375rem",
        lineHeight: "1.28",
        fontWeight: "700",
      },
      h3: {
        fontSize: "1.125rem",
        lineHeight: "1.3",
        fontWeight: "600",
      },
      h4: {
        fontSize: "1rem",
        lineHeight: "1.35",
        fontWeight: "600",
      },
    },
  },

  defaultRadius: "sm",

  // DESIGN.md SS5 Buttons: "6px radius (sm) -- sharper than a typical
  // consumer app... never pill-shaped." Cards get the one exception (lg,
  // 12px) reserved for the reconciliation summary tiles.
  radius: {
    xs: "4px",
    sm: "6px",
    md: "8px",
    lg: "12px",
    xl: "16px",
  },

  // DESIGN.md SS4 Elevation: flat by default, earning elevation only for
  // the nav/content hairline and the applicant-detail drawer overlay.
  // Mantine's `shadow` prop is still used by a few default components
  // (Drawer, Popover) so these stay defined, but tinted toward Deep Harbor
  // Ink (#0c181d) rather than generic black, and kept far more subtle than
  // v1's teal-tinted shadows -- most surfaces in this system use zero
  // shadow at all (the Earned Elevation Rule).
  shadows: {
    xs: "0 1px 0 0 #d9dfe2",
    sm: "0 1px 0 0 #d9dfe2",
    md: "-8px 0 24px rgba(12, 24, 29, 0.10)",
    lg: "-8px 0 24px rgba(12, 24, 29, 0.10)",
    xl: "-8px 0 24px rgba(12, 24, 29, 0.14)",
  },

  // DESIGN.md SS4 Focus Ring: a double ring (white gap + cobalt ring),
  // applied globally so every keyboard-focusable Mantine control gets it
  // for free, not just the ones with a manually-added CSS rule.
  focusRing: "always",

  components: {
    Table: {
      defaultProps: {
        verticalSpacing: "sm",
      },
    },
    Card: {
      // DESIGN.md SS5 Cards: 12px radius (lg) is the one shared shape
      // token; background/border/shadow are left to each call site
      // because the Card component is used for two genuinely different
      // things in this app -- the reconciliation summary tiles (Steel
      // Surface, no border, no shadow -- background contrast is the whole
      // signal) and the login page's own elevated card (white, hairline
      // border, a real earned shadow, since it is the one place in the
      // app that legitimately floats over a page background). Forcing one
      // bg/shadow default here would be wrong for one of the two.
      defaultProps: {
        radius: "lg",
      },
    },
    Badge: {
      // Existing semantic status vocabulary (SS2 "Status vocabulary") is
      // untouched -- this only sets the shape (6px radius) every badge
      // already effectively used, made explicit and consistent.
      defaultProps: {
        radius: "sm",
      },
    },
  },
});

export { SYSTEM_SANS, SYSTEM_MONO };
