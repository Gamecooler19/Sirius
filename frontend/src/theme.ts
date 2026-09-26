/**
 * Module 12 visual redesign: Mantine theme overrides. Before this module,
 * `<MantineProvider>` (`App.tsx`) had zero customization -- default blue
 * primary, default radii, default (system) font stack, indistinguishable
 * from a fresh `npx mantine` scaffold. This file is the one place that
 * changes; no component's data-fetching, role gating, or RLS-scoped query
 * logic is touched by anything here.
 *
 * Palette rationale: a cool cyan/teal accent, not Mantine's default blue
 * and not the generic "AI-purple" the redesign skill explicitly flags.
 * Chosen to sit visually apart from every semantic status color already
 * in use across the app (`STATUS_COLORS` in ApplicantsPage/FinancePage:
 * gray/blue/yellow/orange/grape/green/red/dark) so the brand accent never
 * collides with or gets mistaken for a status badge -- a real risk with a
 * generic blue primary sitting next to a blue "APPLIED" badge.
 */

import { createTheme, type MantineColorsTuple } from "@mantine/core";

const sirius: MantineColorsTuple = [
  "#e6fcf9",
  "#c3f5ee",
  "#9aece2",
  "#6de2d5",
  "#45d9ca",
  "#22c7b5",
  "#159e91",
  "#0c7a70", // primary shade (index 7): 5.21:1 contrast against white,
  // passes WCAG AA (4.5:1) for the white text Mantine's filled Button
  // variant uses by default -- shade 5 (#22c7b5, the visually "brightest"
  // brand teal) was checked first and only hits 2.12:1, a real
  // accessibility failure caught by computing actual contrast ratios
  // rather than eyeballing the color, per the redesign skill's mandatory
  // "Button Contrast Check".
  "#065c54",
  "#02423c",
];

export const theme = createTheme({
  primaryColor: "sirius",
  colors: { sirius },
  primaryShade: 7,

  fontFamily: "Geist, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  fontFamilyMonospace:
    "'Geist Mono', ui-monospace, SFMono-Regular, Consolas, monospace",

  headings: {
    fontFamily: "Geist, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    fontWeight: "600",
    sizes: {
      // Tighter tracking + slightly heavier weight than Mantine's default
      // gives headings real presence without the display-serif or
      // oversized-hero treatment that would be wrong for a data-dense
      // admin tool (see this module's report: registry read as "product",
      // not "landing page").
      h1: { fontSize: "2rem", lineHeight: "1.2", fontWeight: "700" },
      h2: { fontSize: "1.5rem", lineHeight: "1.3", fontWeight: "600" },
      h3: { fontSize: "1.25rem", lineHeight: "1.35", fontWeight: "600" },
      h4: { fontSize: "1.1rem", lineHeight: "1.4", fontWeight: "600" },
    },
  },

  defaultRadius: "md",

  // One shape system, applied everywhere (redesign skill: "Pick ONE
  // corner-radius scale for the page and stick to it"). Mantine's own
  // "md" token (8px) becomes the single radius every component inherits
  // by default; nothing below hand-picks a different radius per
  // component.
  radius: {
    xs: "4px",
    sm: "6px",
    md: "8px",
    lg: "12px",
    xl: "16px",
  },

  shadows: {
    // Tinted toward the brand hue rather than pure black, per the
    // redesign skill ("tint shadows to match the background hue").
    xs: "0 1px 2px rgba(6, 60, 55, 0.06)",
    sm: "0 2px 6px rgba(6, 60, 55, 0.08)",
    md: "0 4px 12px rgba(6, 60, 55, 0.10)",
    lg: "0 8px 24px rgba(6, 60, 55, 0.12)",
    xl: "0 16px 40px rgba(6, 60, 55, 0.14)",
  },

  components: {
    // Emil Kowalski: buttons must feel responsive to press. The actual
    // scale(0.97) tactile-feedback rule lives in `index.css`
    // (`.mantine-Button-root:active`), applied globally via CSS rather
    // than per-component so every button in the app gets it for free,
    // including ones added by future modules -- no `components.Button`
    // override needed here for that specific rule.
    Table: {
      defaultProps: {
        verticalSpacing: "sm",
      },
    },
    Card: {
      defaultProps: {
        radius: "lg",
      },
    },
  },
});
