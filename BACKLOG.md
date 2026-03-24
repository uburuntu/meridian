# Backlog

Prioritized task list for Meridian development.
Version history is in [CHANGELOG.md](CHANGELOG.md).

---

## P0 — Critical

### Security

- [ ] **Ping link leaks server IP to third party** — connection page links to `getmeridian.org/ping?ip=SERVER_IP`, exposing the real IP in URL params and server logs. Fix: route through local endpoint or use fragment `#ip=...` (`templates/connection-info.html.j2:270`, `render.py:432`)
- [ ] **Realm binary no checksum verification** — downloaded from GitHub without integrity check. Pin SHA256 digests per version/arch in `config.py`, verify after download (`provision/relay.py:221-244`)
- [ ] **Silent host key acceptance in non-interactive mode** — `_verify_host_key` falls back to auto-accept when no TTY (`ssh.py:111-114`). Should `fail()` instead; add `--trust-host-key` flag for explicit opt-in
- [ ] **All scanned host key types trusted, only one shown to user** — `ssh-keyscan` returns multiple key types but user only verifies one fingerprint; all are written to `known_hosts` (`ssh.py:119-124`). Write only the verified key
- [ ] **Connection page missing `<meta name="referrer">`** — unlike website pages, connection-info.html.j2 has no referrer policy. Footer/ping clicks leak server path in `Referer` header

### Anti-censorship

- [ ] **IP cert fingerprinting via Caddy catch-all** — active probers sending non-Reality SNI to port 443 get routed to Caddy, which returns a Let's Encrypt IP certificate. No legitimate CDN does this — strong detection signal. Need a default TLS cert strategy that mimics the camouflage target or closes non-matching connections
- [ ] **XHTTP URL missing `sni=` in direct mode** — client infers SNI from raw IP, Caddy serves IP cert. Active probers can distinguish this from any real service (`protocols.py:218`)
- [ ] **Relay topology fully exposed in connection pages** — both relay URLs and "BACKUP (DIRECT)" URLs containing exit IP are listed together, exposing the full topology to anyone with the page (`connection-info.html.j2:172-188`)

### Product

- [ ] **`meridian client show NAME`** — regenerate/re-display connection info without recreating the client (different UUID = revoked). Most common support need for tech friends
- [ ] **Subscription URL support** — `subEnable` in 3x-ui for auto-config refresh on IP change. Without it, every rebuild requires manually resharing QR codes with every user. Core resilience gap vs Outline/Amnezia
- [ ] **Client migration for rebuilds** — `meridian rebuild NEW_IP --from OLD_IP` or `meridian client migrate` to re-add all clients from old server credentials. The IP-blocked rebuild workflow is the most painful moment and has no tooling

### Reliability

- [ ] **No service health monitoring after deploy** — 3x-ui Docker has no `HEALTHCHECK`, Xray can crash inside the container without restart. No watchdog cron. Add 5-min health check cron similar to stats cron (`provision/docker.py`, `provision/services.py`)
- [ ] **IP cert renewal depends on Caddy staying alive** — 6-day shortlived certs, no monitoring if Caddy dies. HAProxy/Caddy systemd units have no explicit `Restart=on-failure` added by provisioner (`provision/services.py:180-259`)

### Code quality

- [ ] **Magic email-prefix strings in stats script bypass protocol registry** — `update-stats.py` hardcodes `startswith('reality-')` instead of using `INBOUND_TYPES` (`provision/services.py:337-343`). Inject from registry
- [ ] **`ProvisionContext._state` untyped dict** — ~15 string keys accessed across files with no schema. Promote to typed Optional fields on the dataclass (`provision/steps.py:57-78`)

---

## P1 — High

### Security

- [ ] **Stats script credential URL-encoding** — panel password interpolated without `urllib.parse.quote()` in generated Python script. Latent auth bug if password alphabet changes (`provision/services.py:316`)
- [ ] **Wildcard CORS on connection pages** — `Access-Control-Allow-Origin: *` lets any website `fetch()` private connection page content (`provision/services.py:158,240`). Remove or restrict to same-origin
- [ ] **Stats files world-readable** — `chmod 644` on `/var/www/private/stats/{uuid}.json` reveals traffic patterns and last-online timestamps. Use `chmod 600` + authenticated endpoint (`provision/services.py:383`)
- [ ] **Cookie file race window** — panel cookie created world-readable by curl, then `chmod 600` in separate SSH call. Pre-create with `umask 077` (`panel.py:51-60`)
- [ ] **`install.sh` double curl-pipe-bash** — pipes `uv` installer from `astral.sh` without checksum. Pin version + verify hash (`install.sh:49`)
- [ ] **Realm config world-readable with exit IP** — `realm.toml` at `chmod 644` contains exit server IP in plaintext. Change to `chmod 600` (`provision/relay.py:286`)

### Anti-censorship

- [ ] **Default SNI `www.microsoft.com` is heavily monitored** — most popular Reality target, GFW actively fingerprints it. ASN mismatch with VPS providers is instant detection signal. Make `meridian scan` the strongly recommended default, not a secondary option
- [ ] **Docker pull during deploy is a fingerprinting signal** — `ghcr.io/mhsanaei/3x-ui` pull from GitHub CR within hours of VPS provisioning is a strong proxy-setup indicator. Consider pre-caching or using a less distinctive registry
- [ ] **`spiderX: "/"` hardcoded** — universal default across all Xray deployments, GFW can fingerprint. Randomize or derive from camouflage target (`provision/xray.py:103,144`)
- [ ] **`generated_at` timestamp in connection page footer** — reveals exact deployment time, aids timeline correlation (`connection-info.html.j2:280`)
- [ ] **"Powered by Meridian" + GitHub link on connection pages** — identifies the tool to anyone viewing the page. Add `--no-branding` deploy option

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
- [ ] **Stats cron runs as root with no error output or alerting** — silent failures leave stats stale. Add `2>&1 | logger` or `MAILTO` (`provision/services.py:309-391`)
- [ ] **Relay systemd unit missing `StartLimitBurst`** — infinite restart loop on persistent failure causes log flooding (`provision/relay.py:32-46`)
- [ ] **Disk space pre-check missing from provisioner** — `preflight` checks disk but `deploy` doesn't. Add 2GB threshold guard at pipeline start

### UX / Accessibility

- [ ] **Connection page has no ARIA landmarks or keyboard support** — all-div structure, clickable URLs use `onclick` on non-interactive elements, invisible to screen readers. Add landmarks, `role="button"`, `tabindex`, `keydown` handlers
- [ ] **Connection page QR alt text is generic** — `alt="QR code for connection"` doesn't distinguish protocols. Use `alt="QR code — VLESS Reality, client alice"`
- [ ] **Connection page `<html lang="en">` hardcoded** — RTL for Farsi applied only after JS executes, causing LTR flash on slow connections. Set `lang`/`dir` server-side via template variable
- [ ] **Connection page font sizes too small for mobile** — `.6rem`/`.65rem` (~10px) fails WCAG 1.4.4. Minimum `.75rem` (12px) for all visible text
- [ ] **`prefers-reduced-motion` missing** — scroll-reveal animations on landing page, `scroll-behavior: smooth` — both need media query override
- [ ] **CommandBuilder keyboard navigation** — ARIA `tablist` pattern missing arrow-key navigation between tabs
- [ ] **Language picker has no `aria-pressed` state** — active language is visual-only, invisible to screen readers
- [ ] **Farsi i18n gaps** — missing keys, English loanword "idempotent" used without explanation, docs links point to `/docs/en/` regardless of active language
- [ ] **Connection page `document.execCommand('copy')` deprecated** — broken on iOS 16.4+. Replace fallback with visible input for manual copy

### Code quality

- [ ] **`protocols` field typed as `dict[str, Any]`** — forces runtime isinstance guards. Use `dict[str, ProtocolConfig]` union type (`credentials.py:98`)
- [ ] **ValueError instead of fail()** — `client.py:208,401,475` raise ValueError for internal bugs instead of styled error output. Extract `_get_reality_protocol()` helper
- [ ] **URL construction duplicated** — `DeployConnectionPage` hand-builds VLESS URLs duplicating `protocols.py` logic. Use `build_protocol_urls()` from `urls.py` (`provision/services.py:759-810`)
- [ ] **Jinja2 listed as dev-only dep but required at runtime** — `render.py` fallback path never tested in CI. Move to hard runtime dependency or test fallback (`pyproject.toml:39`)
- [ ] **`SimpleNamespace(stdout=...)` QR hack** — cargo-culted artifact. Template should use plain string directly (`render.py:291-297`)
- [ ] **`StepResult.status` type safety** — use `Literal["ok", "changed", "skipped", "failed"]` or `StrEnum` (`provision/steps.py:22`)

---

## P2 — Medium

### Security

- [ ] **`_is_on_server()` leaks IP-lookup activity** — `curl ifconfig.me` from client machine visible to ISP/DPI as VPN-setup fingerprint (`ssh.py:341`, `resolve.py:26`). Add self-hosted IP echo at `getmeridian.org/ip`
- [ ] **Unquoted sysctl values in shell commands** — BBR `sed`/`echo` don't use `shlex.quote()`, violating project convention. Latent injection pattern (`provision/common.py:231-232`)
- [ ] **`mkdir exist_ok` ignores mode on existing dir** — credential dir permissions not enforced if already exists with wrong mode (`credentials.py:169`). Explicitly `chmod 0o700` after mkdir
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
- [ ] **`qrencode` install or louder failure** — install script should include it, or failure message should include exact install command for detected OS

### Reliability

- [ ] **SSH `ConnectTimeout=5` too aggressive** — intercontinental deploys can timeout. Increase to 10s or add one retry (`ssh.py:16`)
- [ ] **No `docker compose pull` on re-deploy** — existing server re-run may reuse cached old image when digest changes but tag stays the same
- [ ] **`_wait_for_panel` doesn't distinguish SSH timeout from unhealthy panel** — polling loop can break on transient SSH issues (`provision/panel.py:397-424`)
- [ ] **E2E mocks systemctl as no-op** — service supervision never tested. Hides regressions in systemd integration (`tests/e2e/mock-systemctl.sh`)

### UX

- [ ] **Connection page `<noscript>` fallback missing** — without JS: no translations, no copy buttons, no stats, broken for Farsi
- [ ] **"BACKUP (DIRECT)" label hardcoded English** — not translatable, needs `data-t` key (`connection-info.html.j2:187`)
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

- [ ] **`confirm()` raises Exit(1) on "n"** — can't distinguish rejection from failure, can't do cleanup. Should return bool (`console.py:82-97`)
- [ ] **`_sync_credentials_to_server()` silently ignores SCP failures** — stale server credentials on sync failure. Return bool, retry once (`client.py:77-98`, `relay.py:110-129`)
- [ ] **Global `_qrencode_warned` flag poisons test isolation** — module-level mutable state makes tests order-dependent (`urls.py:14`)
- [ ] **`InstallCaddy` 11-parameter constructor** — resolved at `run()` from context anyway. Remove redundant constructor params or split subclasses (`provision/services.py:504-532`)
- [ ] **No test coverage for wizard or provisioner integration** — `_interactive_wizard`, `_check_ports`, `_offer_relay` untested. Add mocked tests (`tests/test_setup.py`)
- [ ] **`detect_public_ip()` called multiple times with no caching** — adds 3-6s latency. Use `@lru_cache` (`resolve.py:23-39`)
- [ ] **Duplicate atomic-write pattern** — `_save_relay_local()` duplicates `ServerCredentials.save()` tempfile+rename. Extract helper (`relay.py:80-107`)

### Website

- [ ] **CLI docs missing flags** — `--domain`, `--sni`, `--user` for `preflight`/`test`/`doctor`; `--server` for `deploy`; `--name`/`--user` for `server add` — update `cli-reference.md` in all 4 locales
- [ ] **Sitemap i18n hreflang** — add `i18n` option to `sitemap()` in `astro.config.mjs`
- [ ] **Twitter card `summary_large_image`** — change `twitter:card` in `Base.astro`
- [ ] **Dark mode toggle** — system-preference only, no manual override
- [ ] **CSS sync activation** — `connection-info.html.j2` markers + `sync-template-css.mjs` in CI
- [ ] **Accordion body translations** — ~50 hardcoded EN keys
- [ ] **CommandBuilder status messages i18n** — hint text hardcoded EN
- [ ] **GenAI images** — fresh OG, logo, favicon, connection page
- [ ] **Docs sidebar on mobile** — no alternative navigation below 860px
- [ ] **`og:locale` meta tag** — missing for non-English pages
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
- [ ] **`meridian serve` local web UI** — `localhost:PORT` for client management via GUI. Bridges gap vs Outline Manager
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

- [x] ~~Re-deploy context loading~~
- [x] ~~WSS inbound port=0~~
- [x] ~~Non-atomic credential writes~~
- [x] ~~Panel login cookie ordering~~
- [x] ~~SSH host key verification (TOFU prompt)~~
- [x] ~~Docker image digest pinning~~
- [x] ~~RealiTLScanner checksum verification~~
- [x] ~~`confirm()` defaults to yes without TTY~~
- [x] ~~Public IP detection consolidation~~
