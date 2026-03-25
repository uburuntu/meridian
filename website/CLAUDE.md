# website — Astro static site (getmeridian.org)

```bash
cd website && npm install && npm run build   # Astro + Pagefind
```

## Design decisions

**Why Astro** — static generation means every page is a flat HTTP request. Content collections integrate natively with markdown docs. File-based routing. Minimal JS shipped (islands architecture).

**i18n strategy** — docs are per-locale markdown files (`src/content/docs/{locale}/`). Landing page uses client-side `data-t` attribute swapping. English is baked into HTML; non-EN languages swap at runtime. This is asymmetric but avoids shipping EN translations in JS.

**Self-hosted everything** — fonts (woff2), no CDN, no Google. Zero external requests. Target users live in censored regions where external resources are blocked.

**Machine-readable endpoints** — `/llms.txt` (AI index), `/llms-full.txt` (all docs concatenated), `/md/[slug]` (raw markdown per doc), `/context-hub.md`. These make the project AI-native.

## Website ↔ CLI relationship

- **App links**: `src/data/apps.json` is SOT. CI validates against template + Python constants.
- **AI docs**: en/ markdown → `make ai-docs` → bundled `ai-reference.md`. CI generates automatically.
- **install.sh**: deployed to `getmeridian.org/install.sh` by CI release workflow.

## Pitfalls

- **Language switch reload asymmetry** — EN reloads page (build-time HTML), non-EN does client-side DOM swap. Consolidating would simplify but requires shipping EN translations.
- **Pagefind only works after build** — dev mode shows fallback search input.
- **Docs must exist in all 4 locales** — missing locale file breaks sidebar generation.
- **Early locale script in `<head>`** — detects lang from localStorage, sets `dir=rtl` for Farsi before paint. Prevents layout shift.
