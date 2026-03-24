# PWA Connection Page

Server-hosted Progressive Web App that replaces the old monolithic `connection-info.html.j2` for server-deployed pages. The original template is kept for local-save pages only.

## File roles

| File | Type | Role |
|------|------|------|
| `app.js` | Static JS | All rendering logic, platform detection, deep links, i18n, clipboard, PWA APIs |
| `styles.css` | Static CSS | Full styling with responsive breakpoints (460/720/960px), dark/light mode |
| `sw.js` | Static JS | Service worker: cache-first for shell, network-first for config/stats |
| `icon.svg` | Static SVG | Single maskable icon for PWA manifest |
| `index.html.j2` | Jinja2 | Lightweight shell (~35 lines). Only `client_name` and `asset_path` baked in |
| `manifest.webmanifest.j2` | Jinja2 | Per-client manifest with client name in title |

## Architecture

- **`index.html`** is a skeleton shell — no credentials, no protocol data
- **`config.json`** (fetched at runtime by `app.js`) contains all connection data: protocols, QR codes, relays, apps list
- **`sub.txt`** is a standard V2Ray subscription (base64-encoded URL list)
- **Shared assets** (`app.js`, `styles.css`, `sw.js`, `icon.svg`) deployed once to `/var/www/private/pwa/`
- **Per-client files** deployed to `/var/www/private/{uuid}/`

## CSS conventions

- **Responsive breakpoints**: mobile-first, `@media (min-width: 768px)` for tablet, `@media (min-width: 1200px)` for desktop
- **Child combinators for nested `<details>`**: ALWAYS use `.parent > summary` (not `.parent summary`) when styling `<summary>` elements, because nested `<details>` inside collapsed sections will inherit parent summary styles. This caused a real bug where the "More options" chevron icon appeared on nested "Show raw link" toggles.
- **`<details>` marker suppression** requires THREE rules globally:
  ```css
  summary { list-style: none }
  summary::-webkit-details-marker { display: none }
  summary::marker { content: none }
  ```
  Missing any one of these leaves native triangles visible in some browsers.
- **All transitions/animations ≤ 100ms** — snappy feel, no entrance animations. Only exception: skeleton shimmer (loading state).
- **Background**: subtle radial gradient (top glow), no dot grid.
- **Hero card** (`.card-hero`): primary protocol gets accent glow border, larger QR (220px), side-by-side layout on desktop via `.card-body` + `.card-controls`.
- **Compact cards**: QR behind `<details class="qr-expand">` toggle, action-first layout.

## JS conventions

- **No framework, no build step** — vanilla ES5-compatible JS in an IIFE
- **All dynamic content** built as HTML strings and set via `innerHTML` on `#app`
- **`escapeHtml()`** used for ALL user/config data interpolated into HTML. Exception: `qr_b64` validated with regex instead (`/^[A-Za-z0-9+/=]+$/`)
- **iOS deep links** use `data-url` + `data-ios-idx` attributes (never inline JS strings) to avoid XSS from URL content
- **i18n**: translations in `T` object (ru, fa, zh). English is NOT a translation — it's the HTML default. Switching to EN requires full `renderPage()` re-render.
- **Language persistence**: saved to `localStorage('meridian-lang')`, checked before `navigator.language`
- **`isPersonalName()`** filters "default", "demo", "test", "client" from trust bar and title personalization
- **`window._meridianConfig`** stores the fetched config for language switching re-renders

## Testing

```bash
uv run meridian dev preview              # serve with demo data
uv run meridian dev preview --watch      # live reload on source changes
uv run meridian dev preview --name alice # preview with specific client name
uv run pytest tests/test_render_pwa.py tests/test_pwa.py -v  # unit tests
```

Watch mode disables the service worker (replaces with no-op) and injects a polling script that auto-reloads the browser when source files change.

## Common pitfalls

1. **Service worker caches old files** — use `--watch` mode during development, or clear site data in DevTools
2. **`_PWA_APPS` must match `apps.json`** — platform strings must be identical (e.g., `"All platforms"` not `"All"`)
3. **Caddy `@nocache` matcher** — uses `not path` exclusions; an unconditional `header Cache-Control "no-store"` would override all conditional cache headers
4. **Stats URL path** — stats are at `/stats/{uuid}.json` (sibling of client dirs), not `/{uuid}/stats/`
5. **SW scope** — registered with `{scope: '../'}` to control sibling paths; requires `Service-Worker-Allowed: "/"` Caddy header
