# Backlog

Prioritized task list for Meridian development.
Version history is in [CHANGELOG.md](CHANGELOG.md).

---

## P0 — Critical

### Security

- [x] ~~**XSS in inline `onclick` handlers**~~ — Fixed: uses data-* attributes + event delegation
- [x] ~~**No Content-Security-Policy on PWA pages**~~ — Fixed: CSP header in Caddy config
- [x] ~~**`navigator.share()` titles say "VPN"**~~ — Fixed: titles are empty strings
- [x] ~~**Ping link leaks server IP to third party**~~ — By design: IP already visible in VLESS URLs
- [x] ~~**Realm binary no checksum verification**~~ — SHA256 digests pinned in `config.py`, verified after download
- [x] ~~**Silent host key acceptance in non-interactive mode**~~ — now `fail()`s with hint about `ssh-keyscan`
- [x] ~~**All scanned host key types trusted, only one shown to user**~~ — now writes only the preferred/verified key
- [x] ~~**Connection page missing `<meta name="referrer">`**~~ (added in PWA shell template)

### Anti-censorship

- [ ] **IP cert fingerprinting via Caddy catch-all** — active probers sending non-Reality SNI to port 443 get routed to Caddy, which returns a Let's Encrypt IP certificate. No legitimate CDN does this — strong detection signal. Need a default TLS cert strategy that mimics the camouflage target or closes non-matching connections
- [ ] **XHTTP URL missing `sni=` in direct mode** — client infers SNI from raw IP, Caddy serves IP cert. Active probers can distinguish this from any real service (`protocols.py:218`)
- [ ] **Relay topology fully exposed in connection pages** — both relay URLs and "BACKUP (DIRECT)" URLs containing exit IP are listed together, exposing the full topology to anyone with the page (`connection-info.html.j2:172-188`)

### Product

- [ ] **`meridian client show NAME`** — regenerate/re-display connection info without recreating the client (different UUID = revoked). Most common support need for tech friends
- [x] ~~**Subscription URL support** — `subEnable` in 3x-ui for auto-config refresh on IP change~~ (implemented via PWA `sub.txt` subscription endpoint)
- [ ] **Client migration for rebuilds** — `meridian rebuild NEW_IP --from OLD_IP` or `meridian client migrate` to re-add all clients from old server credentials. The IP-blocked rebuild workflow is the most painful moment and has no tooling
- [x] ~~**config.json error state is a dead-end**~~ — Fixed: retry button with i18n
- [x] ~~**SW `networkFirst` returns `undefined` on cache miss**~~ — Fixed: returns 503 Response

### Reliability

- [x] ~~**No service health monitoring after deploy**~~ — added 5-min health watchdog cron (checks Xray/Caddy/HAProxy, restarts on failure, logs to syslog)
- [x] ~~**IP cert renewal depends on Caddy staying alive**~~ — added systemd `Restart=on-failure` drop-in overrides for both HAProxy and Caddy
- [x] ~~**Stats files owned by root:600, Caddy can't serve**~~ — Fixed: 644 perms, stats dir owned by caddy

### Code quality

- [ ] **Magic email-prefix strings in stats script bypass protocol registry** — `update-stats.py` hardcodes `startswith('reality-')` instead of using `INBOUND_TYPES` (`provision/services.py:337-343`). Inject from registry
- [ ] **`ProvisionContext._state` untyped dict** — ~15 string keys accessed across files with no schema. Promote to typed Optional fields on the dataclass (`provision/steps.py:57-78`)

---

## P1 — High

### Security

- [ ] **`connection-info.html.j2` missing `<meta referrer="no-referrer">`** — local-save template has no referrer meta. When opened as local file and user clicks app download links, Referer leaks `file://` path
- [ ] **QR base64 not validated server-side** — `connection-info.html.j2` injects QR data into `<img src>` without regex validation. PWA `app.js` correctly uses `isValidBase64()` — apply same check server-side in `render.py`
- [ ] **`manifest.webmanifest.j2` rendered without autoescape** — `render.py:377` only autoescapes `.html.j2`. Client name with `"` could break JSON structure. Add JSON escaping or autoescape for `.webmanifest.j2`
- [ ] **SW cache never invalidates** — `CACHE_VERSION = 'meridian-pwa-v1'` is hardcoded. Updated `app.js`/`styles.css` never reach existing users. Embed hash or version in cache key during deployment (`sw.js:2`)
- [ ] **`window._meridianConfig` exposes credentials globally** — `app.js:831` stores complete config.json on `window`. Any extension/injected script can read all UUIDs and URLs. Use module-scoped variable instead
- [x] ~~**Stats script credential URL-encoding**~~ — added `urllib.parse.quote()` in generated stats script
- [x] ~~**Wildcard CORS on connection pages**~~ — removed `Access-Control-Allow-Origin: *` from private page Caddy config
- [x] ~~**Stats files world-readable**~~ — changed to `chmod 600`
- [x] ~~**Cookie file race window**~~ — uses `umask 077` in subshell, no separate chmod
- [ ] **`install.sh` double curl-pipe-bash** — pipes `uv` installer from `astral.sh` without checksum. Pin version + verify hash (`install.sh:49`)
- [x] ~~**Realm config world-readable with exit IP**~~ — changed to `chmod 600`

### Anti-censorship

- [ ] **Page title / manifest name "Meridian" identifiable** — `<title>Connection Setup</title>`, manifest `short_name: "Meridian"`, SW cache `meridian-pwa-v1`. If PWA installed on inspected device, immediately identifies circumvention tool. Make naming neutral/configurable
- [ ] **"Powered by Meridian" + GitHub link on connection pages** — identifies the tool to anyone viewing the page, appears in browser history. Add `--no-branding` deploy option or remove entirely (`app.js:526-529`, `connection-info.html.j2:276`)
- [ ] **Default SNI `www.microsoft.com` is heavily monitored** — most popular Reality target, GFW actively fingerprints it. ASN mismatch with VPS providers is instant detection signal. Make `meridian scan` the strongly recommended default, not a secondary option
- [ ] **Docker pull during deploy is a fingerprinting signal** — `ghcr.io/mhsanaei/3x-ui` pull from GitHub CR within hours of VPS provisioning is a strong proxy-setup indicator. Consider pre-caching or using a less distinctive registry
- [ ] **`spiderX: "/"` hardcoded** — universal default across all Xray deployments, GFW can fingerprint. Randomize or derive from camouflage target (`provision/xray.py:103,144`)
- [ ] **`generated_at` timestamp in connection page footer** — reveals exact deployment time, aids timeline correlation (`connection-info.html.j2:280`)

### Product

- [ ] **No VPS provider guide** — zero guidance on SSH key creation, OS selection, IP retrieval. First real blocker for Tier 1 tech friends. Add 300-word "Getting your first VPS" doc page
- [ ] **Wizard hardening prompt before SSH key validation** — can lock out users with password-only SSH access. Check key auth before offering hardening, or add validation step (`setup.py`)
- [ ] **Connection page has no plain-language explanation** — drops non-technical users directly into "scan QR code" without explaining what the app does or why it's safe. Add 2-3 trust-building sentences
- [ ] **`client list` with no usage stats** — no last-seen, traffic totals, or active/inactive indicator. 3x-ui API has `getClientTraffics/{email}` — surface it
- [ ] **No `client disable`/`client enable`** — revocation is all-or-nothing. Panel API supports enable/disable per client, just needs CLI exposure
- [ ] **Proactive IP block detection** — server self-checks against `getmeridian.org/ping`, notifies via webhook/Telegram. Promote from Icebox to active backlog
- [ ] **Rebuild state transfer** — `meridian deploy NEW_IP --from OLD_IP` copies scanned SNI, domain config, client list from old credentials

### Reliability

- [ ] **Provisioner aborts on first failure with no recovery guidance** — user left in inconsistent state. Add "resume from step N" or explicit safe-to-re-run messaging (`provision/steps.py:118-121`)
- [ ] **`InstallDocker` skips when containers running, regardless of image version** — re-deploy doesn't pull new 3x-ui image if tag unchanged but digest differs. No `docker compose pull` on re-deploy (`provision/docker.py:62-71`)
- [x] ~~**Stats cron runs as root with no error output or alerting**~~ — added `| logger -t meridian-stats` for syslog capture
- [x] ~~**Relay systemd unit missing `StartLimitBurst`**~~ — added `StartLimitIntervalSec=300` and `StartLimitBurst=5`
- [x] ~~**Disk space pre-check missing from provisioner**~~ — added `CheckDiskSpace` step (2GB threshold) as first pipeline step

### UX / Accessibility

- [ ] **No RTL CSS support for Farsi** — `dir=rtl` is set in JS but CSS uses `margin-left/right`, `text-align:left/right` everywhere. All directional properties need logical equivalents (`margin-inline-start/end`, `text-align:start/end`) or `[dir=rtl]` overrides (`styles.css`)
- [ ] **Toast "Copied" never translated** — hardcoded in `index.html.j2:25`, outside `#app` container, `applyI18n()` never touches it
- [ ] **CSS "Click to copy" tooltip hardcoded English** — `styles.css:429` uses CSS pseudo-element `content:'Click to copy'`, untranslatable via `data-t`
- [ ] **iOS deep link hardcodes v2RayTun, Android hardcodes Hiddify** — inconsistent, confusing if user installed different app. "Open in App" should use `vless://` scheme (both apps register) or let user choose (`app.js:148-171`)
- [ ] **Toast invisible to screen readers** — no `role="alert"` or `aria-live` on toast element (`index.html.j2:25`)
- [ ] **Connection page has no ARIA landmarks or keyboard support** — all-div structure, clickable URLs use `onclick` on non-interactive elements, invisible to screen readers. Add landmarks, `role="button"`, `tabindex`, `keydown` handlers
- [ ] **Connection page QR alt text is generic** — `alt="QR code"` doesn't distinguish protocols. Use `alt="QR code — Primary connection"` with protocol label
- [ ] **Connection page `<html lang="en">` hardcoded** — RTL for Farsi applied only after JS executes, causing LTR flash on slow connections. Set `lang`/`dir` server-side via template variable
- [ ] **Connection page font sizes too small for mobile** — `.6rem`/`.65rem` (~10px) fails WCAG 1.4.4. Minimum `.75rem` (12px) for all visible text
- [ ] **Language button touch targets too small** — `.lang-btn` has `padding:3px 8px` at `.68rem`, well under 44x44px minimum (WCAG 2.5.8) (`styles.css:97`)
- [x] ~~**`prefers-reduced-motion` missing**~~ — added media query for scroll-reveal and smooth scrolling
- [ ] **CommandBuilder keyboard navigation** — ARIA `tablist` pattern missing arrow-key navigation between tabs
- [ ] **Language picker has no `aria-pressed` state** — active language is visual-only, invisible to screen readers
- [x] ~~**Farsi i18n gaps**~~ — fixed docs links to use locale-specific paths; `updateDocsLinks()` rewrites `/docs/en/` on language switch
- [ ] **Connection page `document.execCommand('copy')` deprecated** — broken on iOS 16.4+. Replace fallback with visible input for manual copy

### Code quality

- [ ] **Silent template failures return empty string** — `render.py:370,390` catches bare `Exception` and returns `""`. User gets empty `index.html` deployed with no error. Add logging, re-raise, or return sentinel
- [ ] **`upload_client_files()` should use base64 transport** — uses raw `printf '%s'` with `shlex.quote()` for multi-KB content, could exceed `ARG_MAX`. Align with `upload_pwa_assets()` which uses base64 (`pwa.py:79`)
- [ ] **`pwa.py` mkdir return codes unchecked** — `conn.run("mkdir -p ...")` at lines 74, 116 doesn't check `returncode`. Disk full or permission errors give confusing downstream failures
- [ ] **Zero test coverage: upload pipeline** — `upload_client_files()`, `upload_pwa_assets()`, `_deploy_client_page()`, `_regenerate_client_pages()` have no tests. Security-sensitive shell command construction untested (`pwa.py`, `client.py:101-138`, `relay.py:132-188`)
- [ ] **Zero test coverage: `DeployConnectionPage` success path** — ~80 lines of URL building, QR generation, stats setup, cron, PWA upload untested (`services.py:827-1003`)
- [ ] **Zero test coverage: `_render_stats_script()`** — complex embedded Python script with YAML parsing, HTTP, file I/O. Not a single test (`services.py:311-440`)
- [ ] **Caddy XHTTP block untested** — both IP and domain config tests never pass `xhttp_path`/`xhttp_internal_port` (`test_services.py`)
- [ ] **No unit test syncing `_PWA_APPS` with `apps.json`** — CI validates template refs but no test catches Python constant drift (`render.py:231-236`)
- [ ] **Manifest color mismatch** — `manifest.webmanifest.j2` uses `#0c0e14`, CSS and `index.html.j2` use `#14161E`. Causes visible PWA splash screen flash
- [ ] **Massive Caddy config duplication** — `_render_caddy_config()` and `_render_caddy_ip_config()` are nearly identical (~100 lines each). Extract shared connection-page/headers/logging block (`services.py:92-303`)
- [ ] **Protocol card hero/non-hero code duplication** — `renderProtocolCard()` has ~85 lines of identical HTML in both branches, only differ by CSS class (`app.js:545-677`)
- [ ] **`protocols` field typed as `dict[str, Any]`** — forces runtime isinstance guards. Use `dict[str, ProtocolConfig]` union type (`credentials.py:98`)
- [ ] **ValueError instead of fail()** — `client.py:208,401,475` raise ValueError for internal bugs instead of styled error output. Extract `_get_reality_protocol()` helper
- [ ] **URL construction duplicated** — `DeployConnectionPage` hand-builds VLESS URLs duplicating `protocols.py` logic. Use `build_protocol_urls()` from `urls.py` (`provision/services.py:759-810`)
- [ ] **Jinja2 listed as dev-only dep but required at runtime** — `render.py` fallback path never tested in CI. Move to hard runtime dependency or test fallback (`pyproject.toml:39`)
- [ ] **`SimpleNamespace(stdout=...)` QR hack** — cargo-culted artifact. Template should use plain string directly (`render.py:291-297`)
- [x] ~~**`StepResult.status` type safety**~~ — `StepStatus = Literal["ok", "changed", "skipped", "failed"]` type alias added

---

## P2 — Medium

### Security

- [ ] **`_is_on_server()` leaks IP-lookup activity** — `curl ifconfig.me` from client machine visible to ISP/DPI as VPN-setup fingerprint (`ssh.py:341`, `resolve.py:26`). Add self-hosted IP echo at `getmeridian.org/ip`
- [x] ~~**Unquoted sysctl values in shell commands**~~ — now uses `shlex.quote()` + `printf` instead of `echo`
- [x] ~~**`mkdir exist_ok` ignores mode on existing dir**~~ — explicitly `chmod 0o700` after mkdir
- [ ] **Panel cookie at predictable non-temp path** — `$HOME/.meridian/.cookie` shared across concurrent processes. Use `tempfile.mkstemp` per session, namespaced by server IP (`panel.py:36`)

### Anti-censorship

- [ ] **XHTTP path length is predictable** — 16 lowercase-alphanumeric chars is a narrow entropy class detectable via HTTP/2 DPI. Add random prefix segment or vary length (`provision/panel.py:106`)
- [ ] **`packet-up` XHTTP mode creates asymmetric traffic pattern** — bursty upstream + streaming downstream detectable through traffic analysis. Consider offering `stream-up` alternative
- [ ] **DNS queries to `8.8.8.8` during provisioning** — monitored by Roskomnadzor/Iran DPI. Use system resolver or allow configurable DNS (`provision/services.py:922`)

### Product

- [ ] **Batch client add** — `meridian client add alice bob charlie` with single panel session. Essential for post-rebuild workflows (`commands/client.py`)
- [ ] **Per-client traffic/IP limits** — expose `--limit-gb` and `--limit-ip` flags on `client add`. Backend plumbing exists in 3x-ui API
- [ ] **Connection page self-hosted ping** — `/ping` endpoint on server itself for connectivity testing when `getmeridian.org` is blocked in the user's region
- [ ] **Windows WSL setup guide** — undocumented. Common platform in Russia/Iran. Add doc page
- [ ] **`meridian server status`** — multi-server overview: alive, client count, relay count, last activity. All data available via existing panel API
- [ ] **Domain mode Cloudflare detection in preflight** — detect orange-cloud-too-early by checking returned IP against Cloudflare ASNs
- [ ] **`meridian test --via RELAY_IP`** — end-to-end TLS handshake test through relay, not just TCP check
- [ ] **`meridian client export NAME`** — generate standalone HTML file with connection info for offline sharing via messaging apps (Signal, Telegram attachments). Bypasses URL filters in censored environments
- [ ] **`qrencode` install or louder failure** — install script should include it, or failure message should include exact install command for detected OS

### Reliability

- [ ] **SSH `ConnectTimeout=5` too aggressive** — intercontinental deploys can timeout. Increase to 10s or add one retry (`ssh.py:16`)
- [ ] **No `docker compose pull` on re-deploy** — existing server re-run may reuse cached old image when digest changes but tag stays the same
- [ ] **`_wait_for_panel` doesn't distinguish SSH timeout from unhealthy panel** — polling loop can break on transient SSH issues (`provision/panel.py:397-424`)
- [ ] **E2E mocks systemctl as no-op** — service supervision never tested. Hides regressions in systemd integration (`tests/e2e/mock-systemctl.sh`)

### UX

- [x] ~~**Connection page `<noscript>` fallback missing**~~ (added in PWA shell template)
- [x] ~~**"BACKUP (DIRECT)" label hardcoded English**~~ (added `data-t` key in PWA `app.js`)
- [ ] **Farsi question mark uses ASCII `?` instead of `؟`** — undermines trust with native Farsi speakers (`app.js:73`)
- [ ] **Multi-protocol labels use jargon** — "XHTTP", "via relay", "Routes through CDN" meaningless to non-tech users. Better: "Connection 1 (try first)", "Connection 2 (backup)"
- [x] ~~**Clock sync warning shown even when clock is OK**~~ — removed informational clock warning; only shown when skew detected
- [x] ~~**Subscription URL shown to all users**~~ — moved behind `<details>` toggle
- [ ] **`<title>` never updated on language switch** — stays English "Connection Setup" after switching to Russian/Farsi/Chinese
- [ ] **"via {name}" hardcoded English preposition** — should be "через" (RU), "از طریق" (FA). Add to translation dict (`app.js:425-426`)
- [ ] **`index.html` not in SW precache list** — first offline visit after SW install fails because HTML isn't cached (`sw.js:3-7`)
- [ ] **Click-to-copy URL divs have no keyboard support** — `.url` and `.sub-url-value` use `onclick` on `<div>` with no `tabindex`, `role`, or `keydown` handler
- [ ] **`apple-touch-icon` uses SVG** — iOS doesn't support SVG for touch icons, requires PNG. Icon won't appear on iOS home screen (`index.html.j2:15`)
- [x] ~~**Flag emoji in language selector**~~ — replaced with language names (English, Русский, فارسی, 中文)
- [ ] **QR images 200x200px marginal on high-DPI** — generate 400x400px minimum for Retina displays
- [ ] **Connection page stats strings English-only** — "Active now", "Active Xm ago" not in translation object
- [ ] **Wizard `_confirm_scan()` silently fails on WSL** — `/dev/tty` read catches `OSError` with no user feedback
- [ ] **Wizard doesn't validate SSH user input** — shell metacharacters accepted, cause downstream errors
- [ ] **Relay offer defaults to N** — inconsistent with other wizard prompts defaulting to Y, hides useful resilience feature
- [ ] **Docs links in translations point to `/docs/en/`** — Russian/Farsi/Chinese users get English docs links
- [ ] **Landing page i18n doesn't update `<title>` or OG meta tags** — shared links show English previews
- [ ] **Mobile nav missing Escape key handler and focus management** — keyboard navigation broken
- [ ] **Client-side language switching uses `innerHTML`** — XSS surface if translations ever loaded externally

### Code quality

- [ ] **`config.json` schema not validated in tests** — no test checks required fields (`key`, `label`, `url`, `qr_b64`, `recommended`) or relay sub-fields
- [ ] **Measure test coverage** — run `pytest --cov` and add coverage badge to README. Replace vague "480+ tests" with an actual coverage percentage
- [ ] **Unicode/non-ASCII client names never tested** — given target audience (Iran/China/Russia), Cyrillic/Farsi/CJK names are real-world scenarios
- [ ] **`confirm()` raises Exit(1) on "n"** — can't distinguish rejection from failure, can't do cleanup. Should return bool (`console.py:82-97`)
- [ ] **`_sync_credentials_to_server()` silently ignores SCP failures** — stale server credentials on sync failure. Return bool, retry once (`client.py:77-98`, `relay.py:110-129`)
- [ ] **Global `_qrencode_warned` flag poisons test isolation** — module-level mutable state makes tests order-dependent (`urls.py:14`)
- [ ] **`InstallCaddy` 11-parameter constructor** — resolved at `run()` from context anyway. Remove redundant constructor params or split subclasses (`provision/services.py:504-532`)
- [ ] **No test coverage for wizard or provisioner integration** — `_interactive_wizard`, `_check_ports`, `_offer_relay` untested. Add mocked tests (`tests/test_setup.py`)
- [ ] **`detect_public_ip()` called multiple times with no caching** — adds 3-6s latency. Use `@lru_cache` (`resolve.py:23-39`)
- [ ] **Duplicate atomic-write pattern** — `_save_relay_local()` duplicates `ServerCredentials.save()` tempfile+rename. Extract helper (`relay.py:80-107`)

### Website

- [x] ~~**CLI docs missing flags**~~ — Fixed: all deploy flags documented, CI validates sync
- [ ] **Live GitHub stars count in trust bar** — fetch via GitHub API or embed shields.io badge. Current trust bar uses static text
- [ ] **Sitemap i18n hreflang** — add `i18n` option to `sitemap()` in `astro.config.mjs`
- [x] ~~**Twitter card `summary_large_image`**~~ — changed `twitter:card` in `Base.astro`
- [x] ~~**Landing page Reference section redundant**~~ — removed 7 accordion items duplicated in docs pages, replaced with CTA
- [x] ~~**Landing page trust/credibility bar**~~ — static indicators (MIT, tests, languages, open source) between Hero and How It Works
- [x] ~~**Landing page final CTA**~~ — closing call-to-action section with install + docs links before Footer
- [x] ~~**README positioning section**~~ — "Why Meridian?" comparison table vs Marzban/Hiddify/raw 3x-ui
- [x] ~~**README architecture diagram placement**~~ — moved above CLI reference for natural reading flow
- [x] ~~**README CLI reference trimming**~~ — 8 essential commands, link to docs for full list
- [x] ~~**GitHub topics stale**~~ — removed `ansible` (purged v3.3.0), added `anti-censorship`, `vpn`, `censorship-circumvention`, `python`, `cli`
- [x] ~~**Landing page section order**~~ — moved Command Builder below Architecture (value proposition before power-user tools)
- [x] ~~**install.sh deprecated command names**~~ — setup→deploy, check→preflight, ping→test, version→--version
- [x] ~~**Architecture diagram 404**~~ — generated SVG from Mermaid source, replaced broken PNG reference
- [x] ~~**Locale-aware docs links**~~ — `updateDocsLinks()` rewrites `/docs/en/` on language switch, fixed translation strings
- [x] ~~**GitHub Discussions disabled**~~ — enabled with default categories
- [ ] **OG image shows old domain** — `og.png` displays `getmeridian.com`; needs regeneration with `getmeridian.org`
- [ ] **Connection page screenshot shows old domain** — `connection-page.png` shows stale domain in browser bar
- [ ] **GitHub social preview** — no custom OG image set; depends on new og.png
- [ ] **VPS setup guide** — ~300-word doc page for first-time VPS renters (Hetzner, DigitalOcean, SSH keys)
- [ ] **Dark mode toggle** — system-preference only, no manual override
- [ ] **CSS sync activation** — `connection-info.html.j2` markers + `sync-template-css.mjs` in CI
- [ ] **Accordion body translations** — ~50 hardcoded EN keys
- [ ] **CommandBuilder status messages i18n** — hint text hardcoded EN
- [ ] **GenAI images** — fresh OG, logo, favicon, connection page
- [ ] **Docs sidebar on mobile** — no alternative navigation below 860px
- [x] ~~**`og:locale` meta tag**~~ — added to `Base.astro` with proper locale mapping
- [ ] **Footer `/version` endpoint** — fetch fails silently; generate file or remove
- [ ] **Hero image no WebP/AVIF** — plain PNG bypasses Astro optimizer, 30-50% byte savings possible
- [ ] **Font preload missing** — no `<link rel="preload">` for above-fold fonts
- [ ] **CommandBuilder RTL input alignment** — `.builder__input--short` 120px hardcoded, clips in RTL
- [ ] **`aria-current="page"` missing on nav links**

### Existing provisioner/arch items

- [ ] Domain mode E2E test (HAProxy + Caddy + WSS on a server with domain)
- [ ] Provisioner unit tests (mock `conn.run()`, test idempotency) — priority: `ConfigurePanel`, `CreateRealityInbound`, `LoginToPanel`
- [ ] Credential file corruption test (truncated/malformed YAML)
- [ ] **BBR/firewall helpers** — extract shared from `provision/common.py` + `provision/relay.py`
- [ ] **Credential sync** — extract shared `sync_credentials_to_server()`
- [ ] **Connection page deploy** — extract shared `deploy_hosted_page()`
- [ ] **Client name validation** — extract shared validator
- [ ] **UUID generation** — consolidate `panel.py:178` + `provision/panel.py:299`
- [x] ~~**Public IP detection** — consolidate `setup.py` + `ssh.py`~~ (moved to `resolve.py`)
- [ ] **`console.fail()` hint_type type safety** — use `Literal["user", "system", "bug"]`
- [ ] **`PROTOCOL_ORDER` consistency** — pick one iteration pattern
- [ ] **`urls.py`/`render.py` hardcoded protocol keys** — replace with generic dispatch
- [ ] Make protocol abstraction honest — rename to "VLESS transport registry"
- [ ] Extract `PanelTransport` protocol — separate SSH+curl from API semantics
- [ ] `console.fail()` → domain exceptions — `MeridianError` hierarchy
- [ ] Partial client add rollback
- [ ] **Broad `except Exception`** — `scan.py`, `render.py`, `update.py`
- [ ] **Panel context manager** — `provision/panel.py:313` cookie leak on failure
- [ ] **Subprocess timeout** — `update.py:83-110` no timeout
- [ ] **Jinja2 template caching** — re-creates Environment per call
- [ ] **N+1 panel calls** — `find_inbound()` re-fetches list per protocol
- [ ] **14 untested modules** — display.py, ai.py, and many command/provision modules
- [ ] **Test `build_protocol_urls()` directly**
- [ ] **Test `ServerConnection.fetch_credentials()`**
- [ ] **MockUndefined swallows errors** in template tests
- [ ] **`assert` in production code** — `provision/panel.py:223-224`. Replace with `fail()` or conditional return
- [ ] **`Inbound.clients`/`stream_settings` untyped** — `list[dict]`/`dict` should be typed dataclasses
- [ ] **`is_ipv4()` edge cases** — accepts `0.0.0.0`, leading zeros, whitespace. Use `ipaddress.ip_address()` instead

---

## P3 — Nice to have

### Product

- [ ] **Audit log** — when each client was added, by whom, last access. Even `~/.meridian/audit.log` would help Tier 3 orgs
- [ ] **Password-protected connection pages** — HTTP Basic Auth or client-specific token on hosted page. Prevents credential harvesting from intercepted links
- [ ] **Multi-server client management** — client on servers A and B for redundancy. Architecturally deep but core gap for fleet management
- [ ] **Connection page auto-test** — JS that tries each VLESS URL and highlights the working one, instead of manual "try Primary first"
- [x] ~~**`meridian serve` local web UI**~~ (implemented as `meridian dev preview` — local PWA preview with demo data)
- [ ] IPv6 support
- [ ] Batch client add (`meridian client add alice bob charlie`)

### Anti-censorship

- [ ] **Inbound remark names in SQLite** — `VLESS-Reality`, `VLESS-WSS` confirm Meridian on server seizure. Use generic names (`protocols.py:33-47`)
- [ ] **RealiTLScanner binary left in `/tmp` on scan failure** — forensic evidence. Clean up reliably (`scan.py:88-96`)
- [ ] **Landing page `<title>` contains "Censorship-Resistant Proxy"** — readable in TLS SNI/QUIC headers. Consider neutral title

### Reliability

- [ ] **HAProxy/Caddy missing `LimitNOFILE`** — may hit fd exhaustion on older distros under high traffic
- [ ] **`_is_on_server()` external HTTP on every `detect_local_mode()`** — 3s timeout on every CLI command. Replace with local IP enumeration (`ssh.py:338-350`)
- [ ] **Relay removal doesn't clean binary/config** — `/usr/local/bin/realm` and `/etc/meridian/realm.toml` persist after relay remove

### UX

- [ ] **Getting-started "two minutes" claim** — deploy realistically takes 5-10 minutes. Manage expectations
- [ ] **WSL not defined in docs** — "(Windows Subsystem for Linux)" parenthetical or link needed
- [ ] **Wizard SNI skip option numbering** — invalid selection silently ignored with no feedback
- [ ] **Wizard setup failure message** — raw exception in detail. Truncate and suggest `meridian doctor`

---

## Icebox

- [ ] Key/credential rotation without reinstall
- [ ] Zero-to-VPN onboarding wizard on website
- [ ] Shell completion (typer built-in)
- [ ] Remove v1→v2 credential migration (sunset old format)
- [ ] `conn.run()` complexity — split into `RemoteConnection`/`LocalConnection`
- [ ] `check.py:run()` 234-line monolith — extract checks
- [ ] `client.py:run_add()` 146 lines — extract helpers
- [ ] Caddy repo `any-version` codename — pin to distro codename

---

## Done

Items shipped in releases. See [CHANGELOG.md](CHANGELOG.md) for details.

**3.8.0** — PWA security/a11y/i18n (40 tests), landing page restructure, README positioning, install.sh fix, architecture SVG, locale links, reduced-motion, GitHub topics/discussions
**3.7.4** — Caddy `handle_path` fix for PWA cache headers, mypy/lint fixes
**3.7.2** — local mode, security hardening, reliability (19 items)
**3.7.1** — HAProxy port fix
**3.7.0** — website, provisioner hardening (9 items)
