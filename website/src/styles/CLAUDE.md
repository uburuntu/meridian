# styles — Design token system

## Design decisions

**Tokens in `tokens.css`** — all colors, typography, shadows, radii as CSS custom properties. No hardcoded values elsewhere.

**Light-first, warm palette** — default is warm cream (#FDFAF6). Dark mode via `prefers-color-scheme` uses warm charcoal (#1C1E28), never pure black. Both modes maintain the brand warmth.

**Three font families** — Fraunces (serif headings, editorial feel), Source Sans 3 (body), JetBrains Mono (code). All self-hosted as variable WOFF2. `font-display: swap` prevents invisible text.

**Color naming is generic** — `--ac` (accent), `--t1` (text primary), `--s1` (surface). Requires familiarity but keeps the token set small and composable.

## What's done well

- **Dark mode is a full token remap** — every property has a dark variant. Accent gets lighter, shadows darker. Contrast ratios maintained.
- **Global focus states** — 2px accent outline on all interactive elements. Defined once in `global.css`.

## Pitfalls

- **No manual dark mode toggle** — `prefers-color-scheme` only. Users can't override.
- **No explicit z-index scale** — sticky elements may conflict as layering increases.
- **Shadows hardcode rgba** — should derive from tokens for true dark mode adaptability.
