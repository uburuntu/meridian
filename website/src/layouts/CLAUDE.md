# layouts — Astro page shells

## Design decisions

**Three layouts, one base** — `Base.astro` is the HTML shell (head, nav, footer, i18n bootstrap). `Docs.astro` and `BlogPost.astro` extend it with their own content structure. All pages share the same early `<head>` scripts and global styles.

**Early locale + theme detection** — inline `<script>` in `<head>` reads localStorage before first paint. Sets `lang`, `dir="rtl"` for Farsi, and `data-theme` for dark mode. Prevents layout shift and color flash.

**Docs locale bridge** — `#docs-locales` JSON script tag passes available locale data from Astro (build-time) to the header LanguagePicker (client-side). The picker reads this to navigate between translations.

## What's done well

- **Hreflang links on docs** — Docs layout emits `<link rel="alternate" hreflang>` for each available locale. SEO-correct language signaling.
- **JSON-LD schemas** — Docs has BreadcrumbList, BlogPost has Article schema. Built at render time from props.
- **Markdown alternate link** — Docs layout adds `<link rel="alternate" type="text/markdown">` pointing to `/md/[slug]` for machine consumption.

## Pitfalls

- **Base.astro i18n must stay in sync with `src/i18n/index.ts`** — the early `<head>` script hardcodes the locale map (`{ru,fa,zh}`). If locales change, both files need updating.
- **Docs locale JSON is fragile** — `#docs-locales` is parsed by client JS. If the element is missing or malformed, language switching silently fails on docs pages.
- **RTL is layout-level** — `dir="rtl"` is set on `<html>` in Base and on `.docs-layout` in Docs. Component-level RTL overrides (prose blockquote border, list padding) live in Docs layout styles.
