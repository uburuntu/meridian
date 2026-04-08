# Backlog

Prioritized task list for Meridian development.
Version history is in [CHANGELOG.md](CHANGELOG.md).

---

## Manual / External

Things that require human action outside the codebase.

### Housekeeping

- [ ] **Create 3-5 "good first issue" GitHub issues** — pull from P2 items below to signal contributor-friendliness
- [ ] **Regenerate OG image** — `og.png` shows old domain `getmeridian.com`; needs `getmeridian.org`
- [ ] **Retake connection page screenshot** — `connection-page.png` shows stale domain in browser bar
- [ ] **Set GitHub social preview** — repo Settings > Social preview (depends on new OG image)
- [ ] **Write VPS onboarding guide** — ~300-word doc page: Hetzner/DigitalOcean, Debian 12, SSH keys, IP retrieval

### Launch channels (priority order)

- [x] **Вастрик.Клуб** — [launched 2026-04-02](https://vas3k.club/project/31264/), 78 upvotes, 3k+ views, 100+ GitHub stars overnight
- [ ] **r/selfhosted post** (~350k) — lead with architecture diagram, terminal SVG, demo page. Be upfront about no web UI
- [ ] **Show HN** — "Deploy an undetectable VLESS+Reality proxy in one command". Discuss uTLS, HAProxy SNI, threat model
- [ ] **r/opensource post** (~335k) — mission framing: "help people in censored regions share secure internet"
- [ ] **Censorship expert TG channel post** — author of [state-of-usa-itd](https://habr.com/ru/articles/1014038/) offered to post about Meridian
- [ ] **Niche communities** — r/iran, Telegram V2Ray/Xray groups (Persian, Chinese), r/privacy (engage, don't self-promote)

### Post-launch

- [ ] **Technical blog post** — nginx+Xray architecture deep-dive. Cross-post to dev.to
- [ ] **"Meridian vs raw 3x-ui" comparison page** on website — captures search traffic
- [ ] **Respond to every comment** within 24h of launch posts

---

## P0 — Critical

### Anti-censorship

- [ ] **Relay SNI mismatch** — relay in RU zone inherits exit node's SNI (e.g. microsoft.com). Client connecting to a Russian IP with Microsoft SNI is unrealistic and detectable. Relay deploy should scan its own IP range and pick a locally plausible SNI, independent of exit node
- [ ] **IP cert fingerprinting via nginx catch-all** — active probers get Let's Encrypt IP cert on non-Reality SNI. Need cert strategy that mimics camouflage target or drops connection

### Product

- [x] **`meridian client show NAME`** — regenerate/re-display connection info without recreating client
- [ ] **Client migration for rebuilds** — `meridian rebuild NEW_IP --from OLD_IP` or `meridian client migrate`

### Code quality

- [x] **Magic email-prefix in stats script** — hardcodes `startswith('reality-')` instead of using `INBOUND_TYPES`

---

## P1 — High

### Security

- [ ] **SSH password auth not hardened during provisioning** — cloud-init drops `PasswordAuthentication yes` in `/etc/ssh/sshd_config.d/`, overriding main config. Provisioner should disable password auth and restart sshd after confirming key access works
- [x] **`manifest.webmanifest.j2` no autoescape** — client name with `"` breaks JSON
- [x] **SW cache never invalidates** — hardcoded `CACHE_VERSION`. Embed hash during deployment
- [x] **Silent template failures return `""`** — catch bare `Exception`, deploy empty HTML
- [x] **`_sync_credentials_to_server()` ignores SCP failures** — credentials silently not synced
- [x] **Wizard no SSH user validation** — shell metacharacters accepted (injection risk)

### Anti-censorship

- [ ] **Default SNI `www.microsoft.com` monitored** — ASN mismatch detection. Make `meridian scan` the default
- [x] **`spiderX: "/"` hardcoded** — fingerprint-able. Randomize or derive from camouflage target

### Product

- [ ] **VPS provider guide** — first blocker for Tier 1 "tech friends"
- [ ] **Auto SSH key setup** — when VPS only has password auth, auto-generate key, copy via `ssh-copy-id`, and proceed. Eliminates manual key setup step before deploy
- [ ] **Telegram bot for client management** — add/revoke clients, view stats without SSH. Mobile-friendly for "not at computer" use case
- [ ] **Post-deploy Cloudflare setup guidance** — after domain mode deploy, print step-by-step Cloudflare DNS/SSL setup in CLI output
- [ ] **Add Happ and ShadowRocket to connection page** — popular cross-platform clients, already support VLESS subscription URLs
- [ ] **Wizard hardening before SSH key validation** — can lock out password-only users
- [ ] **Connection page plain-language intro** — 2-3 trust-building sentences before "scan QR"
- [ ] **`client list` with usage stats** — last-seen, traffic totals via 3x-ui `getClientTraffics/{email}`
- [ ] **`client disable`/`client enable`** — panel API supports it, just needs CLI exposure
- [ ] **Proactive IP block detection** — server self-checks via ping endpoint, notifies via webhook/Telegram
- [ ] **Rebuild state transfer** — `meridian deploy NEW_IP --from OLD_IP` copies SNI, domain, clients

### Reliability

- [x] **`InstallDocker` skips regardless of image version** — no `docker compose pull` on re-deploy

### UX

- [x] **`--sni` flag ignored during deploy** — user passes `--sni` but deploy still uses microsoft.com. Flag not plumbed through to config
- [x] **`document.execCommand('copy')` deprecated** — broken on iOS 16.4+

---

## P2 — Medium

### Security

- [x] **Panel cookie predictable path** — shared across concurrent processes. Use `tempfile.mkstemp`
- [ ] **`innerHTML` XSS surface** — risk if translations ever loaded externally

### Anti-censorship

- [x] **DNS `8.8.8.8` during provisioning** — monitored by censors. Use system resolver

### Product

- [ ] **Batch client add** — `meridian client add alice bob charlie`
- [ ] **Per-client traffic/IP limits** — `--limit-gb`, `--limit-ip` flags
- [ ] **Self-hosted ping endpoint** — for when `getmeridian.org` is blocked
- [ ] **Windows WSL setup guide** — doc page
- [ ] **`meridian server status`** — multi-server overview
- [ ] **`meridian test --via RELAY_IP`** — E2E test through relay
- [ ] **`meridian client export NAME`** — standalone HTML for offline sharing
- [ ] **OpenWRT router auto-deploy** — deploy client config directly to OpenWRT routers
- [ ] **Relay on server with existing nginx** — support deploying relay alongside an existing web server on port 443
- [ ] **WebRTC leak warning on connection page** — WebRTC leaks are client-side (browser discovers local IPs via OS APIs, bypassing the proxy entirely). Server-side fixes don't help — traffic never reaches Xray. Add amber warning box to connection page with: 1) link to browserleaks.com/webrtc leak test, 2) per-app guidance (v2rayNG: Global mode, Hiddify: route all connections), 3) browser extension recommendation. Same pattern as clock-sync warning
- [ ] **Replace `qrencode` binary with Python `segno` package** — eliminates system dependency

### Reliability

- [x] **SSH `ConnectTimeout=5` too aggressive** — increase to 10s or add retry
- [ ] **`_wait_for_panel` SSH vs panel confusion** — polling breaks on transient SSH issues

### UX

- [ ] **Multi-protocol jargon** — "XHTTP" meaningless to non-tech. Use "Connection 1 / 2"
- [x] **`<title>` not updated on language switch** — stays English
- [ ] **`index.html` not in SW precache** — first offline visit fails
- [ ] **`apple-touch-icon` uses SVG** — iOS needs PNG
- [x] **QR 200x200px marginal on Retina** — generate 400x400px
- [ ] **Wizard `_confirm_scan()` fails silently on WSL**

### Website

- [ ] **Live GitHub stars in trust bar** — shields.io badge or API fetch
- [x] **Sitemap i18n hreflang** — `i18n` option in `sitemap()` config
- [ ] **Dark mode toggle** — system-preference only, no manual override
- [ ] **Docs sidebar on mobile** — no nav below 860px

---

## Icebox

- [ ] **Amnezia-style app deploy** — download app, enter VPS ip:user:password, auto-deploy without knowing SSH. Full GUI wrapper around `meridian deploy`
- [ ] **Meridian-branded cross-platform client app** — fork Hiddify (Flutter, sing-box, open source, 28k stars) into a stripped-down Meridian client. Subscription URL as primary flow: open app → paste URL / scan QR → connected. Happ is NOT open source (can't fork)
- [ ] **Key/credential rotation without reinstall**
- [ ] **Zero-to-VPN onboarding wizard on website**
- [ ] **Shell completion** — typer built-in
- [ ] **Remove v1→v2 credential migration** — dead code
- [ ] **Remove all Caddy and HAProxy code** — we use nginx, these are dead paths
- [ ] **Accessibility + i18n pass** — RTL CSS, ARIA landmarks, keyboard nav, touch targets, screen reader support, translation completeness (batched from ~20 items)

---

## Done

Collapsed — see [CHANGELOG.md](CHANGELOG.md) for details.

- **3.8.1** — Deploy version tracking + CLI/server mismatch warning, SECURITY.md fix, README docs alignment, CODE_OF_CONDUCT, homepage relay section + og:locale, PWA sub-url toggle + clock warning + flag emoji removal, trust bar cleanup, BACKLOG compaction
- **3.8.0** — PWA security/a11y/i18n (40 tests), landing page restructure, README positioning, install.sh fix, architecture SVG, locale links, reduced-motion, GitHub topics/discussions
- **3.7.4** — Caddy `handle_path` fix for PWA cache headers, mypy/lint fixes
- **3.7.2** — local mode, security hardening, reliability (19 items)
- **3.7.1** — HAProxy port fix
- **3.7.0** — website, provisioner hardening (9 items)
