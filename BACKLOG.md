# Backlog

Prioritized task list for Meridian development.
Version history is in [CHANGELOG.md](CHANGELOG.md).

---

## Next up

### Website (getmeridian.org)

- [ ] **CLI docs missing flags** — `--domain`, `--sni`, `--user` for `preflight`/`test`/`doctor`; `--server` for `deploy`; `--name`/`--user` for `server add` — update `cli-reference.md` in all 4 locales
- [ ] **Sitemap i18n hreflang** — add `i18n` option to `sitemap()` in `astro.config.mjs` for proper `xhtml:link rel="alternate"` entries
- [ ] **Twitter card `summary_large_image`** — change `twitter:card` in `Base.astro` for better OG image display
- [ ] **`prefers-reduced-motion`** — scroll reveal animations on `index.astro` lack reduced-motion media query
- [ ] **CommandBuilder ARIA tabs** — add `role="tabpanel"`, `aria-controls`, `aria-labelledby` for full ARIA tabs pattern
- [ ] **Dark mode toggle** — currently system-preference only, no manual override
- [ ] **CSS sync activation** — add `/* SYNC:START */` / `/* SYNC:END */` markers to `connection-info.html.j2`, run `sync-template-css.mjs` in CI
- [ ] **Accordion body translations** — Reference section content inside accordions is hardcoded EN (~50 keys needed)
- [ ] **CommandBuilder status messages i18n** — interactive hint text is hardcoded EN
- [ ] **GenAI images** — replace old screenshots with fresh OG, logo, favicon, connection page, architecture diagram (prompts in session notes)
- [ ] **Docs sidebar on mobile** — sidebar `display: none` below 860px with no alternative navigation
- [ ] **Clean up unused assets** — `deploy-terminal.svg`, `logo-512.png` not referenced; unused `app.all` translation key
- [ ] **`og:locale` meta tag** — add `<meta property="og:locale">` for non-English pages

### Provisioner hardening

- [x] ~~**Re-deploy context loading** — when `ConfigurePanel` is skipped on re-deploy, `ws_path`/`xhttp_path` aren't loaded into context from saved credentials, breaking Caddy config~~
- [ ] **WSS inbound port=0** — WSS created with `port=0` (undocumented 3x-ui behavior); compute deterministic port like XHTTP
- [ ] **Non-atomic credential writes** — `path.write_text()` risks truncation on crash; use tempfile+rename pattern
- [ ] **Panel login cookie ordering** — `chmod 600` runs before error check; stale cookies on retry cause confusing 403s
- [ ] Domain mode E2E test (HAProxy + Caddy + WSS on a server with domain)
- [ ] Provisioner unit tests (mock `conn.run()`, test idempotency) — priority: `ConfigurePanel`, `CreateRealityInbound`, `LoginToPanel`
- [ ] Credential file corruption test (truncated/malformed YAML)

### Architecture debt

- [ ] Type `ProvisionContext` inter-step state — promote dict keys to typed Optional fields
- [ ] **`PROTOCOL_ORDER` consistency** — some code iterates `PROTOCOLS.values()` directly, others use `PROTOCOL_ORDER`; pick one
- [ ] **`urls.py`/`render.py` hardcoded protocol keys** — `if key == "reality"` branches instead of generic protocol dispatch
- [ ] Make protocol abstraction honest — rename to "VLESS transport registry" (not truly protocol-agnostic)
- [ ] Extract `PanelTransport` protocol — separate SSH+curl transport from 3x-ui API semantics
- [ ] `console.fail()` → domain exceptions — `MeridianError` hierarchy, catch at CLI boundary
- [ ] Partial client add rollback (if Reality succeeds but WSS fails, clean up)
- [ ] Delete stale `output.py` legacy facade
- [ ] **Broad `except Exception`** — in `scan.py`, `render.py:254` (`_load_template_text`), `update.py`; could mask real bugs

### Security hardening

- [x] ~~SSH host key verification — `accept-new` enables TOFU MitM. Switch to prompt-based or `--accept-new-host-key` flag~~
- [ ] Docker image digest pinning — pin to `@sha256:...`
- [ ] RealiTLScanner checksum verification — binary downloaded without integrity check
- [ ] `confirm()` defaults to yes without TTY — destructive ops should default to "no"

### UX improvements

- [ ] `meridian client show NAME` — regenerate connection info without recreating the client
- [ ] `client list` usage stats from 3x-ui API
- [ ] IPv6 support
- [ ] Subscription URL support (`subEnable` for auto-config on IP change)

### Scale features

- [ ] Batch client add (`meridian client add alice bob charlie`)
- [ ] Client migration for rebuilds (detect clients on old server, re-create)
- [ ] Per-client traffic/IP limits (`--limit-gb`, `--limit-ip`)

---

## Icebox

- [ ] Key/credential rotation without reinstall
- [ ] Proactive IP block notification (Telegram/webhook)
- [ ] Zero-to-VPN onboarding wizard on website
- [ ] Password-protected connection info page
- [ ] Shell completion (typer built-in)
- [ ] Remove v1→v2 credential migration (sunset old format)
- [ ] `conn.run()` complexity — split into `RemoteConnection`/`LocalConnection`
- [ ] `check.py:run()` 234-line monolith — extract checks into individual functions
- [ ] `client.py:run_add()` 146 lines — extract helper functions
