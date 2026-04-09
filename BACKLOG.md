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

- [ ] **Client migration for rebuilds** — `meridian rebuild NEW_IP --from OLD_IP` or `meridian client migrate`

### Deployment correctness

- [ ] **`return 444` invalid in nginx HTTP block** — IP-mode deployments use `return 444;` inside an HTTP server block, but 444 only works in stream context. Causes `nginx -t` failure or detectable footprint. Use `return 403;` instead (`services.py:276-278`)
- [ ] **nginx stream block `printf` produces literal `\n`** — single-quoted `\n` in `printf` creates malformed nginx.conf instead of actual newlines. Also appends without guarding against duplicates (`services.py:853-859`)
- [ ] **Socket leak in `tcp_connect()` and `_get_cert_der()`** — sockets not closed on exception path. Repeated connectivity checks (ping, probe) can exhaust file descriptors (`ssh.py:382-394`, `probe.py:88-102`)

---

## P1 — High

### Security

- [ ] **SSH password auth not hardened during provisioning** — cloud-init drops `PasswordAuthentication yes` in `/etc/ssh/sshd_config.d/`, overriding main config. Provisioner should disable password auth and restart sshd after confirming key access works
- [ ] **Firewall cleanup deletes user's custom rules** — `ConfigureFirewall` removes ALL TCP ports not in `{22, 443, 80}`, silently deleting alternate SSH ports, monitoring, or relay listen ports. Should only delete Meridian-managed ports or warn before removing unexpected rules (`common.py:441-458`)
- [ ] **SSRF in icon download** — `urllib.request.urlopen()` in `branding.py:140` doesn't restrict to public IP ranges. Deployer could point at `http://127.0.0.1:2053` to probe internal services. Low risk (deployer-initiated), but should block private/loopback IPs

### Anti-censorship

- [ ] **Default SNI `www.microsoft.com` monitored** — ASN mismatch detection. Make `meridian scan` the default

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

- [ ] **WARP `systemctl enable` and `warp-cli connect` unchecked** — return codes ignored, deployment claims success but WARP not running. Breaks egress routing on WARP-enabled deploys (`warp.py:62, 84, 87`)
- [ ] **`ufw default deny/allow` return codes unchecked** — firewall left in inconsistent state on failure (`common.py:461-462`, `relay.py:117-118`)
- [ ] **Reality port conflict not pre-checked** — in standalone mode (no nginx), Xray binds `0.0.0.0:443` without checking if port is already in use. Panel API succeeds but Xray fails to bind (`xray.py:96, 301`)
- [ ] **`fetch_credentials()` return value ignored** — `setup.py:109` doesn't check SCP result, subsequent code assumes credentials exist

### Code quality

- [ ] **Unused `import hashlib`** — top-level import in `xray_client.py:9` shadowed by local re-import at line 82. Dead code

---

## P2 — Medium

### Security

- [ ] **`innerHTML` XSS surface** — risk if translations ever loaded externally

### Anti-censorship

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

- [ ] **`_wait_for_panel` SSH vs panel confusion** — polling breaks on transient SSH issues
- [ ] **Xray process accumulation on `test_connection()` timeouts** — orphan processes not cleaned up when `_wait_for_port()` times out (`xray_client.py:305-350`)
- [ ] **Broad `except Exception` swallows errors** — silent catch-alls in `urls.py`, `probe.py`, `ping.py`, `update.py` make debugging hard. Should use specific exception types or at least log

### Code quality

- [ ] **IPv6 URLs malformed** — no bracket wrapping in protocol URL builders. `vless://uuid@2001:db8::1:443` is invalid per RFC 3986, needs `[2001:db8::1]` (`protocols.py:178-193`)
- [ ] **Redundant condition check** — `if server_name or icon or color` checked twice in `setup.py:147-157`, inner check always true
- [ ] **Missing type annotation** — `protocol_urls: list` in `client.py:106` should be `list[ProtocolURL]` for consistency
- [ ] **`SystemExit` catch anti-pattern** — `uninstall.py:30-40` catches `SystemExit` from `fail()`. Should use custom exception or optional return

### Testing

- [ ] **14 source modules (34%) have zero tests** — priority gaps: `branding.py` (233 LOC, emoji/image processing), `xray_client.py` (416 LOC, binary download/verify), `ping.py` (244 LOC, reachability), `render.py` (725 LOC, HTML/QR)
- [ ] **`test_render_templates.py` tautological** — 2 tests only check templates don't crash, never verify output content, QR embedding, or variable substitution

### UX

- [ ] **Multi-protocol jargon** — "XHTTP" meaningless to non-tech. Use "Connection 1 / 2"
- [ ] **`index.html` not in SW precache** — first offline visit fails
- [ ] **`apple-touch-icon` uses SVG** — iOS needs PNG
- [ ] **Wizard `_confirm_scan()` fails silently on WSL**

### Website

- [ ] **Live GitHub stars in trust bar** — shields.io badge or API fetch
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

- **3.14** — `client show`, WARP flag, stats script fix, `--sni` plumbing, docker pull on re-deploy
- **3.8.1** — Deploy version tracking, SECURITY.md, CODE_OF_CONDUCT, PWA sub-url toggle + clock warning, trust bar cleanup
- **3.8.0** — PWA security/a11y/i18n (40 tests), landing page, install.sh, architecture SVG, reduced-motion
- **3.7** — Local mode, security hardening (19 items), Caddy/HAProxy fixes, website, provisioner hardening
