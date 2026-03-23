# Meridian — AI Context

Meridian is an open-source CLI tool that deploys censorship-resistant VLESS+Reality proxy servers on any VPS. It uses a pure-Python provisioner that connects via SSH but exposes a simple `meridian` command. Users typically run it from their laptop to configure a remote server.

GitHub: https://github.com/uburuntu/meridian
Website: https://getmeridian.org

## Technology Stack

- **VLESS+Reality** (Xray-core) — proxy protocol that impersonates a legitimate TLS website. Censors probing the server see a real certificate (e.g., from microsoft.com). Only clients with the correct private key can connect.
- **3x-ui** — web panel for managing Xray, deployed as a Docker container. Meridian controls it entirely via REST API.
- **HAProxy** — TCP-level SNI router on port 443 in all modes. Routes traffic by SNI hostname without terminating TLS.
- **Caddy** — reverse proxy with automatic TLS in all modes. In standalone mode, requests a Let's Encrypt IP certificate via ACME `shortlived` profile (6-day validity). Serves connection info pages, reverse-proxies the 3x-ui panel, and proxies both XHTTP (path-based routing) and WSS (domain mode) traffic to Xray.
- **Docker** — runs 3x-ui (which contains Xray). All proxy traffic flows through the Docker container.
- **Pure-Python provisioner** — `src/meridian/provision/` executes deployment steps via SSH. Each step gets `(conn: ServerConnection, ctx: ProvisionContext)` and returns a `StepResult`.
- **uTLS** — impersonates Chrome's TLS Client Hello fingerprint, making connections indistinguishable from real browser traffic.

## Deployment Modes

### Standalone (no domain)

HAProxy on port 443 routes by SNI. Caddy gets a Let's Encrypt IP certificate (ACME `shortlived` profile, 6-day validity) for hosting connection pages, the panel, and XHTTP transport (path-based routing through Caddy).

```
User → Server:443 (HAProxy)
         ├─ SNI matches reality_sni → Xray:10443 (Reality)
         └─ SNI matches server IP   → Caddy:8443 (TLS, IP cert)
                                        ├─ /<info_page_path> → connection page
                                        ├─ /<web_base_path> → 3x-ui panel
                                        └─ /<xhttp_path> → Xray XHTTP (localhost)
```

- 3x-ui panel accessible via HTTPS at a secret path (reverse-proxied by Caddy)
- Connection info page hosted on the server with shareable URLs

### Domain Mode

Adds CDN fallback via Cloudflare. HAProxy on port 443 routes by SNI:

```
User → Server:443 (HAProxy)
         ├─ SNI matches reality_sni → Xray:10443 (Reality)
         └─ SNI matches domain     → Caddy:8443 (TLS)
                                        ├─ /<info_page_path> → connection page
                                        ├─ /<web_base_path> → 3x-ui panel
                                        ├─ /<xhttp_path> → Xray XHTTP (localhost)
                                        └─ /ws-path   → Xray WSS (CDN fallback)
```

- Caddy handles TLS automatically via Let's Encrypt (domain certificate)
- VLESS+WSS routed through Cloudflare CDN as IP-blocking fallback
- Connection info page hosted on the server at `https://domain/<info_page_path>/<uuid>/`

## CLI Commands

```
meridian deploy [IP] [flags]     Deploy proxy server
  --domain DOMAIN               Enable domain mode with CDN fallback
  --email EMAIL                 Email for TLS certificates (optional)
  --sni HOST                    Reality SNI target (default: www.microsoft.com)
  --xhttp / --no-xhttp          XHTTP transport (default: enabled)
  --name NAME                   Name for the first client
  --user USER                   SSH user (default: root)
  --yes                         Skip confirmation prompts

meridian client add|list|remove NAME    Manage client access keys (--server NAME)
meridian server add|list|remove         Manage known servers

meridian relay deploy RELAY_IP --exit EXIT [flags]  Deploy relay node (TCP forwarder)
meridian relay list [--exit EXIT]                   List relay nodes
meridian relay remove RELAY_IP [--exit EXIT]        Remove relay node
meridian relay check RELAY_IP [--exit EXIT]         Check relay health
  --exit/-e EXIT                Exit server IP or name (required for deploy)
  --name NAME                   Friendly name for the relay
  --port/-p PORT                Listen port on relay (default: 443)

meridian preflight [IP] [--ai] [--server NAME]      Pre-flight server validation + ASN check
meridian scan [IP] [--server NAME]               Find optimal SNI targets on server's network
meridian test [IP] [--server NAME]               Test proxy reachability from client device
meridian doctor [IP] [--ai] [--server NAME] Collect system info for debugging (alias: rage)
meridian teardown [IP] [--server NAME]          Remove proxy from server
meridian update                    Update CLI to latest version
meridian --version / -v            Show version
```

Global flag: `--server NAME` targets a specific named server (works with most commands).

## Credential & State Management

- **Server is source of truth**: credentials stored at `/etc/meridian/proxy.yml` on the server
- **Local cache**: `~/.meridian/credentials/<IP>/proxy.yml` per server
- Credentials include: panel login, Reality keys (public/private), client UUIDs, domain, SNI
- **Server registry**: `~/.meridian/servers` tracks known servers (line format: `host user name`)
- On re-runs, saved credentials are loaded (not regenerated) for idempotency

## Key Config Files on Server

| Path | Purpose |
|------|---------|
| `/etc/meridian/proxy.yml` | Saved credentials (panel login, keys, UUIDs, client list) |
| `/etc/caddy/conf.d/meridian.caddy` | Caddy config (all modes) |
| `/etc/haproxy/haproxy.cfg` | HAProxy SNI routing config (all modes) |
| Docker container `3x-ui` | Xray + 3x-ui panel (all modes) |

## Port Assignments

| Port | Service | Mode |
|------|---------|------|
| 443 | HAProxy (SNI router) | All modes |
| 80 | Caddy (ACME challenges) | All modes |
| 10443 | Xray (Reality, internal) | All modes |
| 8443 | Caddy (TLS, internal) | All modes |
| XHTTP port | Xray (XHTTP, localhost only) | When XHTTP enabled |
| WSS port | Xray (WSS, localhost only) | Domain mode |
| 2053 | 3x-ui panel (localhost) | All modes |

XHTTP and WSS inbound ports are internal (localhost only) — Caddy reverse-proxies to them via path-based routing on port 443. No extra external ports are exposed.

## Client Apps

Users connect with these apps after scanning the QR code or importing the VLESS link:

| Platform | App |
|----------|-----|
| iOS | v2RayTun |
| Android | v2rayNG |
| Windows | v2rayN |
| All platforms | Hiddify |
# Meridian — Architecture Reference

## Service Topology

### Standalone Mode (no domain)

```
Internet
  │
  ▼
┌──────────────────────────────────────┐
│ Server                               │
│                                      │
│  Port 443: HAProxy (SNI router)      │
│  ┌──────────────────────────────┐    │
│  │ SNI = reality_sni            │    │
│  │  → Port 10443: Xray (Reality)│    │
│  │                              │    │
│  │ SNI = server IP              │    │
│  │  → Port 8443: Caddy (TLS)   │    │
│  │     ├─ /info-path → page    │    │
│  │     ├─ /panel-path → 3x-ui  │    │
│  │     └─ /xhttp-path → Xray   │    │
│  └──────────────────────────────┘    │
│                                      │
│  Port 80: Caddy (ACME challenges)    │
│                                      │
│  Docker: 3x-ui                       │
│  ├─ Reality inbound (port 10443)     │
│  └─ XHTTP inbound (localhost port)   │
│                                      │
│  Caddy (systemd)                     │
│  └─ IP cert via Let's Encrypt        │
│     (ACME shortlived, 6-day)         │
│                                      │
│  HAProxy (systemd)                   │
│  └─ TCP-level SNI, no TLS terminate  │
└──────────────────────────────────────┘
```

Note: In standalone mode, Caddy requests a Let's Encrypt IP certificate via the ACME `shortlived` profile (6-day validity, auto-renewed). Falls back to self-signed if IP cert issuance is not supported. XHTTP runs on a localhost-only port and is reverse-proxied by Caddy via path-based routing on port 443 — no extra external port is exposed.

### Domain Mode

```
Internet
  │
  ▼
┌──────────────────────────────────────┐
│ Server                               │
│                                      │
│  Port 443: HAProxy (SNI router)      │
│  ┌──────────────────────────────┐    │
│  │ SNI = reality_sni            │    │
│  │  → Port 10443: Xray (Reality)│    │
│  │                              │    │
│  │ SNI = domain                 │    │
│  │  → Port 8443: Caddy (TLS)   │    │
│  │     ├─ /info-path → page    │    │
│  │     ├─ /panel-path → 3x-ui  │    │
│  │     ├─ /xhttp-path → Xray   │    │
│  │     └─ /ws-path → Xray WSS  │    │
│  └──────────────────────────────┘    │
│                                      │
│  Port 80: Caddy (ACME challenges)    │
│                                      │
│  Docker: 3x-ui                       │
│  ├─ Reality inbound (port 10443)     │
│  ├─ XHTTP inbound (localhost port)   │
│  └─ WSS inbound (localhost port)     │
│                                      │
│  Caddy (systemd)                     │
│  └─ Auto TLS via Let's Encrypt       │
│                                      │
│  HAProxy (systemd)                   │
│  └─ TCP-level SNI, no TLS terminate  │
└──────────────────────────────────────┘
```

Key: HAProxy does NOT terminate TLS. It reads the SNI hostname from the TLS Client Hello and forwards the raw TCP stream to the appropriate backend. This allows both Reality (which needs raw TLS) and Caddy (which terminates TLS) to coexist on port 443.

## How Reality Protocol Works

1. Server generates an x25519 keypair. Public key is shared with clients, private key stays on server.
2. Client connects to server on port 443 and sends a TLS Client Hello with SNI set to the camouflage domain (e.g., `www.microsoft.com`).
3. To any observer (DPI, active prober), this looks like a normal HTTPS connection to microsoft.com.
4. If the prober sends their own Client Hello, the server proxies the connection to the real microsoft.com — the prober sees a valid certificate and concludes the server is legitimate.
5. If the client includes a valid authentication (derived from the shared x25519 key) in the Client Hello, the server recognizes it as a proxy client and establishes the VLESS tunnel.
6. uTLS makes the Client Hello byte-for-byte identical to Chrome's, defeating TLS fingerprinting.

## Docker Container Structure

The `3x-ui` Docker container contains:
- **3x-ui web panel** — REST API on port 2053 (internal)
- **Xray binary** at `/app/bin/xray-linux-*` (architecture-dependent path)
- **Database** at `/etc/x-ui/x-ui.db` (SQLite, stores inbound configs and clients)
- **Xray config** managed by 3x-ui (not a static file)

Meridian manages 3x-ui entirely via its REST API:
- `POST /login` — authenticate (form-urlencoded, returns session cookie)
- `POST /panel/api/inbounds/add` — create VLESS inbound
- `GET /panel/api/inbounds/list` — list inbounds (check before creating)
- `POST /panel/setting/update` — configure panel settings
- `POST /panel/setting/updateUser` — change panel credentials

## Caddy Configuration Pattern

Meridian writes to `/etc/caddy/conf.d/meridian.caddy` (never the main Caddyfile). The main Caddyfile gets a single line added: `import /etc/caddy/conf.d/*.caddy`. This allows Meridian to coexist with user's own Caddy configuration.

Caddy handles:
- Auto-TLS certificate (domain cert or Let's Encrypt IP cert via ACME `shortlived` profile)
- Reverse proxy for the 3x-ui panel (at a random web base path)
- Connection info page serving (hosted pages with shareable URLs)
- Reverse proxy for XHTTP traffic to Xray (path-based routing, all modes when XHTTP enabled)
- Reverse proxy for WSS traffic to Xray (domain mode only)

## Provisioning Step Pipeline

Steps execute sequentially via `build_setup_steps()`. Each step gets `(conn, ctx)` and returns a `StepResult`.

| # | Step | Module | Purpose |
|---|------|--------|---------|
| 1 | `InstallPackages` | `common.py` | Install required OS packages |
| 2 | `EnableAutoUpgrades` | `common.py` | Configure unattended-upgrades |
| 3 | `SetTimezone` | `common.py` | Set server timezone to UTC |
| 4 | `HardenSSH` | `common.py` | Disable password auth, harden SSH config |
| 5 | `ConfigureBBR` | `common.py` | Enable TCP BBR congestion control |
| 6 | `ConfigureFirewall` | `common.py` | UFW deny-all + allow 22, 80, 443 |
| 7 | `InstallDocker` | `docker.py` | Install Docker CE |
| 8 | `Deploy3xui` | `docker.py` | Deploy 3x-ui Docker container |
| 9 | `ConfigurePanel` | `panel.py` | Set panel credentials, web base path, settings |
| 10 | `LoginToPanel` | `panel.py` | Authenticate to 3x-ui API |
| 11 | `CreateRealityInbound` | `xray.py` | Create VLESS+Reality inbound on port 10443 |
| 12 | `CreateXHTTPInbound` | `xray.py` | Create VLESS+XHTTP inbound on localhost (routed via Caddy) |
| 13 | `CreateWSSInbound` | `xray.py` | Create VLESS+WSS inbound (domain mode only) |
| 14 | `VerifyXray` | `xray.py` | Verify Xray is running with correct config |
| 15 | `InstallHAProxy` | `services.py` | Install and configure HAProxy SNI routing |
| 16 | `InstallCaddy` | `services.py` | Install Caddy, configure TLS + reverse proxy |
| 17 | `DeployConnectionPage` | `services.py` | Deploy hosted connection page with QR codes |

## Credential Lifecycle

1. **First install**: Meridian generates random credentials (panel password, x25519 keys, client UUID)
2. **Save locally**: Written to `~/.meridian/credentials/<IP>/proxy.yml` BEFORE applying to server (prevents lockout on failure)
3. **Apply to server**: Panel password changed, inbounds created with generated keys
4. **Sync to server**: Credentials copied to `/etc/meridian/proxy.yml` on the server (post_tasks)
5. **Re-runs**: Credentials loaded from local cache, not regenerated (idempotent)
6. **Cross-machine**: `meridian server add IP` fetches credentials from server via SSH
7. **Uninstall**: Credentials deleted from both server and local machine

## File Locations Reference

### On the server
- `/etc/meridian/proxy.yml` — credentials and client list
- `/etc/caddy/conf.d/meridian.caddy` — Caddy config
- `/etc/haproxy/haproxy.cfg` — HAProxy config
- Docker container `3x-ui` — Xray + panel

### On the local machine
- `~/.meridian/credentials/<IP>/` — cached credentials per server
- `~/.meridian/servers` — server registry
- `~/.meridian/cache/` — update check throttle cache
- `~/.local/bin/meridian` — CLI entry point (installed via uv/pipx)

## Relay topology

A relay node is a lightweight TCP forwarder (Realm binary) that runs on a domestic server. Client connects to relay IP, relay forwards raw TCP to exit server on port 443. All encryption is end-to-end between client and exit — relay never sees plaintext. All protocols (Reality, XHTTP, WSS) work through the relay.

Deploy: `meridian relay deploy RELAY_IP --exit EXIT_IP`
Health check: `meridian relay check RELAY_IP`
Remove: `meridian relay remove RELAY_IP`
# Meridian — Troubleshooting Guide

## Which Tool to Use

```
BEFORE INSTALL           → meridian preflight IP
  "Will this server work for Meridian?"
  Tests: SNI reachability, port 443, DNS, OS, disk space.

AFTER INSTALL, CAN'T CONNECT → meridian test IP
  "Is the proxy reachable from where I am right now?"
  Tests: TCP port 443, TLS handshake (Reality), domain HTTPS.
  No SSH needed — runs from the client device.

AFTER INSTALL, SOMETHING BROKE → meridian doctor IP
  "Collect everything for debugging."
  Collects: server OS, Docker, 3x-ui logs, ports, firewall, SNI, DNS.

Add --ai to preflight or doctor for an AI-ready prompt.
```

## Symptom: Can't Connect at All

### Port 443 not reachable (test fails on TCP check)

**Causes:**
1. Cloud provider firewall / security group blocks port 443 inbound
2. ISP or network blocks the server IP entirely
3. Server is down or proxy is not running
4. UFW on the server doesn't allow port 443

**Fixes:**
1. Check cloud provider console — ensure port 443/TCP is allowed inbound
2. Try from a different network (mobile data, another Wi-Fi) to rule out local ISP blocking
3. SSH into the server and check: `docker ps` (is 3x-ui running?), `ss -tlnp sport = :443` (is anything listening?)
4. Check UFW: `ufw status` — should show 443/tcp ALLOW

### TLS handshake fails (test passes TCP but fails TLS)

**Causes:**
1. Xray is not running inside the Docker container
2. Port 443 is occupied by another service (not Xray/HAProxy)
3. Reality SNI target is unreachable from the server (breaks Reality protocol)

**Fixes:**
1. Check Xray: `docker logs 3x-ui --tail 20` — look for errors
2. Check what's on port 443: `ss -tlnp sport = :443` — should be xray, haproxy, or 3x-ui
3. Test SNI target: `meridian preflight IP --sni www.microsoft.com`

### Domain not reachable (test passes Reality but fails domain HTTPS)

**Causes:**
1. DNS not pointing to server IP
2. Caddy not running or failed to get TLS certificate
3. HAProxy not routing domain SNI correctly

**Fixes:**
1. Check DNS: `dig +short yourdomain.com @8.8.8.8` — should return server IP
2. Check Caddy: `systemctl status caddy`, `journalctl -u caddy --no-pager -n 20`
3. Check HAProxy: `systemctl status haproxy`, look at `/etc/haproxy/haproxy.cfg`

## Symptom: Connection Drops After a Few Seconds

**Causes:**
1. System clock skew >30 seconds between client device and server
2. MTU issues on the network path
3. ISP performing connection reset after detecting long-lived TLS sessions

**Fixes:**
1. Sync clock: on server `timedatectl set-ntp true`, on client device check automatic time setting
2. Try a different network to rule out MTU/ISP issues
3. In domain mode, try the WSS/CDN connection link — it routes through Cloudflare and avoids direct IP detection

## Symptom: Setup Fails

### Port 443 conflict

**Cause:** Another service (Apache, Nginx, etc.) is using port 443.

**Fix:** Stop the conflicting service or run Meridian on a clean server. `meridian preflight IP` will tell you what's using the port.

### Xray fails to start (invalid JSON / MarshalJSON error)

**Cause:** The 3x-ui inbound `settings` or `streamSettings` fields contain corrupted JSON. This happens when the `settings` field is sent as a nested object instead of a JSON string — the 3x-ui Go struct expects a `string` type for these fields. The API returns `success: true` but stores only the first key name (e.g., `"clients"`) instead of the full JSON object.

**Fix:** `PanelClient` always sends `settings` as a JSON string inside the JSON body (double-serialized). If you hit this on an older version, uninstall and reinstall: `meridian teardown IP && meridian deploy IP`. To verify the database is clean: `sqlite3 /opt/3x-ui/db/x-ui.db "SELECT settings FROM inbounds;"` — each field should be valid JSON, not a single word.

### XHTTP inbound creation fails (port already exists)

**Cause:** In older versions (pre-v3.6.0), both Reality TCP and XHTTP tried to bind port 443 or used a separate external port. 3x-ui rejects duplicate ports.

**Fix:** Update to v3.6.0+. XHTTP now runs on a localhost-only port and is routed through Caddy via path-based routing on port 443. No extra external port is needed.

### Docker installation fails

**Cause:** Conflicting Docker packages (docker.io, containerd from distro repos).

**Fix:** Meridian auto-removes conflicting packages, but if Docker is already running with containers, it skips installation to avoid disruption. Remove old Docker manually if needed: `apt remove docker.io containerd runc`

### Disk space insufficient

**Cause:** Less than 2GB free disk space.

**Fix:** Free up space: `docker system prune -af`, `journalctl --vacuum-time=1d`, check for large files in `/var/log/`

### DNS resolution fails (domain mode)

**Cause:** Domain doesn't resolve to server IP yet.

**Fix:** Update DNS A record to point to server IP. DNS propagation can take up to 48 hours but usually 5-15 minutes. Meridian will warn you if DNS doesn't resolve but lets you proceed.

### SSH connection errors

**Cause:** SSH key not accepted, server unreachable, or wrong user.

**Fix:** Test SSH manually: `ssh root@SERVER_IP`. Ensure you have key-based access (not just password). Use `--user` flag if not root.

## Symptom: Was Working, Now Stopped

**Causes:**
1. Server IP got blocked by ISP/government — very common in censored regions
2. Server rebooted and Docker didn't auto-start
3. Let's Encrypt certificate expired (domain mode, rare — Caddy auto-renews)
4. 3x-ui database grew too large (unlikely — weekly cron vacuum)

**Fixes:**
1. Run `meridian test IP` — if TCP fails, the IP is likely blocked. Use the WSS/CDN link (domain mode) or deploy a new server
2. SSH in and check: `docker ps` — if 3x-ui is not listed, run `docker start 3x-ui`
3. Check Caddy logs: `journalctl -u caddy --no-pager -n 20`
4. Check disk: `df -h /`

## Symptom: Slow Speeds

**Causes:**
1. Geographic distance between user and server (high latency)
2. Server overloaded (too many clients, high CPU)
3. ISP throttling VPN-like traffic patterns
4. Suboptimal routing

**Fixes:**
1. Choose a server geographically closer to users. Recommended: Finland, Netherlands, Sweden, Germany for Europe/Middle East
2. Check server load: `htop` or `uptime`. Consider a higher-spec VPS
3. Try WSS/CDN link (domain mode) — routes through Cloudflare, may have better routing
4. Enable BBR (Meridian enables it by default): verify with `sysctl net.ipv4.tcp_congestion_control`

## SNI Target Selection

The SNI target is the domain that Reality impersonates. Choosing the wrong one can increase detection risk, though current evidence (IMC 2022, net4people, 2026 research) shows censors rely more on behavioral analysis than IP→domain validation.

**Good SNI targets** (global CDN, shared hosting infrastructure):
- `www.microsoft.com` (default) — Azure CDN, global presence
- `www.twitch.tv` — Fastly CDN, global
- `dl.google.com` — Google CDN, global
- `github.com` — Fastly CDN, global

**Bad SNI targets** (proprietary ASN):
- `apple.com`, `icloud.com` — Apple controls its own ASN ranges. IP/ASN mismatch is a known research-identified detection vector.
- Small/niche single-IP websites — unusual for a VPS IP to serve them.

**Options for SNI selection:**
1. **Global CDN domain** (default) — safe, widely used, no ASN mismatch with major CDN providers
2. **Same-network domain** via `meridian scan` — finds domains on your subnet for ASN consistency
3. **Self-steal** (your own domain) — run a real website, use Reality to masquerade as yourself. Eliminates all IP/ASN/cert mismatches. Requires domain mode (`--domain`). Meridian's domain mode partially supports this — future versions may add full self-steal.

**What actually matters more than SNI choice:** The real detection threat in 2026 is post-handshake behavioral analysis (traffic patterns, packet timing, session duration). XHTTP transport (`--xhttp`) directly addresses this by making tunnel traffic look like normal HTTP browsing. SNI choice is secondary.

## Interpreting `meridian preflight` Output

| Check | What It Tests | If It Fails |
|-------|--------------|-------------|
| SNI target reachability | Can the server reach the camouflage site (e.g., microsoft.com)? | Server's outbound is restricted. Try a different SNI target with `--sni` |
| SNI ASN match | Does the SNI target share a CDN/ASN with the server? | Use a global CDN domain (microsoft.com, twitch.tv, github.com). Avoid apple.com (Apple-owned ASN, instant detection) |
| Port 443 availability | Is port 443 free or used by Meridian? | Another service is on 443. Stop it or use a clean server |
| Port 443 external reachability | Can the outside world reach port 443? | Cloud firewall blocks it. Open port 443/TCP inbound |
| Domain DNS | Does the domain resolve to server IP? | Update DNS A record |
| Server OS | Is it Ubuntu/Debian? | Other distros may work but are untested |
| Disk space | At least 2GB free? | Free up space |

## Interpreting `meridian doctor` Output

| Section | What to Look For |
|---------|-----------------|
| Local Machine | OS compatibility |
| Server | OS version, uptime (recent reboot?), disk/memory usage |
| Docker | Is 3x-ui container running? Status should be "Up" |
| 3x-ui Logs | Error messages, "failed to start" entries, certificate issues |
| Listening Ports | Port 443 should show xray, haproxy, or 3x-ui. If missing, proxy isn't running |
| Firewall (UFW) | Port 443/tcp should be ALLOW. If not listed, it's blocked |
| SNI Target | Should show CONNECTED with a certificate chain. If unreachable, Reality can't work |
| Domain DNS | Should resolve to server IP. If different or empty, DNS is misconfigured |

## Interpreting `meridian test` Output

| Check | Pass | Fail |
|-------|------|------|
| TCP port 443 | Server is network-reachable | Firewall, ISP block, or server down |
| TLS handshake | Reality protocol is working | Xray not running, port conflict, or SNI issue |
| Domain HTTPS | Caddy + HAProxy working | DNS, Caddy, or HAProxy issue |

**If all test checks pass but VPN client still can't connect:**
- Re-scan the QR code or re-import the VLESS link
- Ensure device clock is accurate (within 30 seconds)
- Try a different VPN app (v2rayNG, Hiddify)
- Check that the app is using the Reality link, not an old/invalid one
