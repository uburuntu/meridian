# website — Astro static site (getmeridian.org)

## Build

```bash
cd website && npm install && npm run build   # Astro + Pagefind
```

## Structure

```
astro.config.mjs          Astro config (sitemap, rehype-mermaid, i18n)
src/pages/                Landing, demo, ping, 404, docs/[...slug]
src/components/           Nav, Hero, CommandBuilder, Accordion, CodeBlock, etc.
src/layouts/              Base.astro, Docs.astro
src/styles/               fonts.css, tokens.css, global.css
src/i18n/                 Client-side i18n (translations.ts, index.ts)
src/content/docs/{en,ru,fa,zh}/  48 markdown doc pages (12 per locale)
src/data/apps.json        App download links (single source of truth)
public/fonts/             Self-hosted woff2 (Fraunces, Source Sans 3, JetBrains Mono)
public/img/               Images, terminal SVG, logos
scripts/sync-template-css.mjs  CSS sync between Astro tokens and Jinja2 template
```

## Website ↔ CLI relationship

- **App download links**: `src/data/apps.json` is SOT, CI validates against `connection-info.html.j2`. Also propagated to `render.py:_PWA_APPS` and `app.js:osMap`
- **AI docs**: human docs (en/) → `make ai-docs` → `src/meridian/data/ai-reference.md` (strips frontmatter, concatenates). CI generates automatically
- **i18n**: landing page uses client-side `data-t` + JS swap; docs are server-rendered per-locale files

## Conventions

- **Self-hosted fonts**: zero external requests (Google Fonts blocked in target regions)
- **Referrer policy**: `<meta name="referrer" content="no-referrer">` on all pages
- **Demo data**: use RFC 5737 IPs (`198.51.100.x`), never real server IPs
- **install.sh**: deployed to `getmeridian.org/install.sh` by CI. References in docs are correct, not dangling
- **CSS sync**: `scripts/sync-template-css.mjs` keeps Astro tokens and Jinja2 template styles aligned
