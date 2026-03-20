# Meridian — AI Context

Meridian is an open-source CLI tool that deploys censorship-resistant VLESS+Reality proxy servers on any VPS. It uses Ansible under the hood but exposes a simple `meridian` command. Users typically run it from their laptop to configure a remote server.

GitHub: https://github.com/uburuntu/meridian
Website: https://meridian.msu.rocks

## Technology Stack

- **VLESS+Reality** (Xray-core) — proxy protocol that impersonates a legitimate TLS website. Censors probing the server see a real certificate (e.g., from microsoft.com). Only clients with the correct private key can connect.
- **3x-ui** — web panel for managing Xray, deployed as a Docker container. Meridian controls it entirely via REST API.
- **HAProxy** — TCP-level SNI router (domain mode only). Routes traffic on port 443 by SNI hostname without terminating TLS.
- **Caddy** — reverse proxy with automatic Let's Encrypt TLS (domain mode only). Serves the connection info page and proxies WSS traffic.
- **Docker** — runs 3x-ui (which contains Xray). All proxy traffic flows through the Docker container.
- **Ansible** — automation engine. Meridian downloads playbooks and runs them locally against the target server via SSH.
- **uTLS** — impersonates Chrome's TLS Client Hello fingerprint, making connections indistinguishable from real browser traffic.

## Deployment Modes

### Standalone (no domain)

Simplest mode. Xray listens directly on port 443.

```
User → Server:443 (VLESS+Reality) → Internet
```

- 3x-ui panel accessible via SSH tunnel only (binds to localhost)
- Connection info saved as local HTML file with QR codes

### Domain Mode

Adds CDN fallback and a hosted connection page. HAProxy on port 443 routes by SNI:

```
User → Server:443 (HAProxy)
         ├─ SNI matches reality_sni → Xray:10443 (Reality)
         └─ SNI matches domain     → Caddy:8443 (TLS)
                                        ├─ /connection → info page
                                        └─ /ws-path   → Xray WSS (CDN fallback)
```

- Caddy handles TLS automatically via Let's Encrypt
- VLESS+WSS routed through Cloudflare CDN as IP-blocking fallback
- Connection info page hosted on the server at `https://domain/connection`

### Chain Mode

Two servers for IP whitelist bypass (e.g., Russia → Germany):

```
User → Relay:443 (VLESS+TCP, plain) → Exit:443 (VLESS+Reality+XHTTP) → Internet
```

- Relay is on a whitelisted IP (domestic)
- Exit is abroad and provides actual internet access
- Exit also has a direct Reality port (8444) as a fallback

## CLI Commands

```
meridian setup [IP] [flags]     Deploy proxy server
  --domain DOMAIN               Enable domain mode with CDN fallback
  --sni HOST                    Reality SNI target (default: www.microsoft.com)
  --xhttp                       Add XHTTP transport (enhanced behavioral stealth)
  --name NAME                   Server display name
  --user USER                   SSH user (default: root)
  --yes                         Skip confirmation prompts

meridian client add|list|remove NAME    Manage client access keys
meridian server add|list|remove         Manage known servers
meridian check [IP] [--ai]              Pre-flight server validation + ASN check
meridian scan [IP]                      Find optimal SNI targets on server's network
meridian ping [IP]                      Test proxy reachability from client device
meridian diagnostics [IP] [--ai]        Collect system info for debugging
meridian uninstall [IP]                 Remove proxy from server
meridian self-update                    Update CLI to latest version
meridian version                        Show version
meridian help                           Show help
```

Global flag: `--server NAME` targets a specific named server.

## Credential & State Management

- **Server is source of truth**: credentials stored at `/etc/meridian/proxy.yml` on the server
- **Local cache**: `~/.meridian/credentials/<IP>/proxy.yml` per server
- Credentials include: panel login, Reality keys (public/private), client UUIDs, domain, SNI
- **Server registry**: `~/.meridian/servers` tracks known servers (line format: `host user name`)
- **Playbook cache**: `~/.meridian/playbooks/` with `.version` marker, re-downloaded on CLI update
- On re-runs, saved credentials are loaded (not regenerated) for idempotency

## Key Config Files on Server

| Path | Purpose |
|------|---------|
| `/etc/meridian/proxy.yml` | Saved credentials (panel login, keys, UUIDs) |
| `/etc/meridian/*-clients.yml` | Client list with UUIDs and timestamps |
| `/etc/caddy/conf.d/meridian.caddy` | Caddy config (domain mode) |
| `/etc/haproxy/haproxy.cfg` | HAProxy SNI routing config (domain mode) |
| Docker container `3x-ui` | Xray + 3x-ui panel (all modes) |

## Port Assignments

| Port | Service | Mode |
|------|---------|------|
| 443 | Xray (Reality) | Standalone |
| 443 | HAProxy (SNI router) | Domain |
| 10443 | Xray (Reality, internal) | Domain |
| 8443 | Caddy (TLS, internal) | Domain |
| 2053 | 3x-ui panel (localhost) | All modes |
| 443 | Relay inbound (VLESS+TCP) | Chain |
| 8444 | Exit direct Reality fallback | Chain |

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
┌─────────────────────────┐
│ Server                  │
│                         │
│  Port 443               │
│  ┌───────────────────┐  │
│  │ Docker: 3x-ui     │  │
│  │  └─ Xray (Reality)│  │
│  └───────────────────┘  │
│                         │
│  Port 2053 (localhost)  │
│  └─ 3x-ui Web Panel    │
│    (SSH tunnel only)    │
└─────────────────────────┘
```

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
│  │     ├─ /connection → info    │    │
│  │     ├─ /panel-path → 3x-ui  │    │
│  │     └─ /ws-path → Xray WSS  │    │
│  └──────────────────────────────┘    │
│                                      │
│  Docker: 3x-ui                       │
│  ├─ Reality inbound (port 10443)     │
│  └─ WSS inbound (random port, local) │
│                                      │
│  Caddy (systemd)                     │
│  └─ Auto TLS via Let's Encrypt       │
│                                      │
│  HAProxy (systemd)                   │
│  └─ TCP-level SNI, no TLS terminate  │
└──────────────────────────────────────┘
```

Key: HAProxy does NOT terminate TLS. It reads the SNI hostname from the TLS Client Hello and forwards the raw TCP stream to the appropriate backend. This allows both Reality (which needs raw TLS) and Caddy (which terminates TLS) to coexist on port 443.

### Chain Mode

```
┌─────────────────┐         ┌─────────────────────┐
│ Relay (Russia)  │         │ Exit (Germany)       │
│ Whitelisted IP  │         │                      │
│                 │  VLESS   │                      │
│ Port 443        │ Reality  │ Port 443             │
│ VLESS+TCP ──────┼─XHTTP──→│ Xray (Reality+XHTTP) │
│ (plain, no TLS) │         │                      │
│                 │         │ Port 8444            │
└─────────────────┘         │ Xray (Reality direct) │
                            └─────────────────────┘
```

- User → Relay: plain VLESS+TCP (domestic traffic, no encryption needed)
- Relay → Exit: VLESS+Reality+XHTTP (looks like normal HTTPS to censors on the international link)
- Exit port 8444: direct Reality fallback when relay is not needed

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
- Auto-TLS certificate for the domain
- Reverse proxy for WSS traffic to Xray
- Reverse proxy for the 3x-ui panel (at a random web base path)
- Connection info page serving

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
- `/etc/meridian/proxy.yml` — credentials
- `/etc/meridian/*-clients.yml` — client list
- `/etc/caddy/conf.d/meridian.caddy` — Caddy config
- `/etc/haproxy/haproxy.cfg` — HAProxy config
- Docker container `3x-ui` — Xray + panel

### On the local machine
- `~/.meridian/credentials/<IP>/` — cached credentials per server
- `~/.meridian/playbooks/` — Ansible playbooks cache
- `~/.meridian/servers` — server registry
- `~/.meridian/cache/` — update check, AI docs cache
- `~/.local/bin/meridian` — CLI binary
# Meridian — Troubleshooting Guide

## Which Tool to Use

```
BEFORE INSTALL           → meridian check IP
  "Will this server work for Meridian?"
  Tests: SNI reachability, port 443, DNS, OS, disk space.

AFTER INSTALL, CAN'T CONNECT → meridian ping IP
  "Is the proxy reachable from where I am right now?"
  Tests: TCP port 443, TLS handshake (Reality), domain HTTPS.
  No SSH needed — runs from the client device.

AFTER INSTALL, SOMETHING BROKE → meridian diagnostics IP
  "Collect everything for debugging."
  Collects: server OS, Docker, 3x-ui logs, ports, firewall, SNI, DNS.

Add --ai to check or diagnostics for an AI-ready prompt.
```

## Symptom: Can't Connect at All

### Port 443 not reachable (ping fails on TCP check)

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

### TLS handshake fails (ping passes TCP but fails TLS)

**Causes:**
1. Xray is not running inside the Docker container
2. Port 443 is occupied by another service (not Xray/HAProxy)
3. Reality SNI target is unreachable from the server (breaks Reality protocol)

**Fixes:**
1. Check Xray: `docker logs 3x-ui --tail 20` — look for errors
2. Check what's on port 443: `ss -tlnp sport = :443` — should be xray, haproxy, or 3x-ui
3. Test SNI target: `meridian check IP --sni www.microsoft.com`

### Domain not reachable (ping passes Reality but fails domain HTTPS)

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

**Fix:** Stop the conflicting service or run Meridian on a clean server. `meridian check IP` will tell you what's using the port.

### Docker installation fails

**Cause:** Conflicting Docker packages (docker.io, containerd from distro repos).

**Fix:** Meridian auto-removes conflicting packages, but if Docker is already running with containers, it skips installation to avoid disruption. Remove old Docker manually if needed: `apt remove docker.io containerd runc`

### Disk space insufficient

**Cause:** Less than 2GB free disk space.

**Fix:** Free up space: `docker system prune -af`, `journalctl --vacuum-time=1d`, check for large files in `/var/log/`

### DNS resolution fails (domain mode)

**Cause:** Domain doesn't resolve to server IP yet.

**Fix:** Update DNS A record to point to server IP. DNS propagation can take up to 48 hours but usually 5-15 minutes. Override with `-e skip_dns_check=true` if you're sure it will propagate.

### Ansible connection errors

**Cause:** SSH key not accepted, server unreachable, or wrong user.

**Fix:** Test SSH manually: `ssh root@SERVER_IP`. Ensure you have key-based access (not just password). Use `--user` flag if not root.

## Symptom: Was Working, Now Stopped

**Causes:**
1. Server IP got blocked by ISP/government — very common in censored regions
2. Server rebooted and Docker didn't auto-start
3. Let's Encrypt certificate expired (domain mode, rare — Caddy auto-renews)
4. 3x-ui database grew too large (unlikely — weekly cron vacuum)

**Fixes:**
1. Run `meridian ping IP` — if TCP fails, the IP is likely blocked. Use the WSS/CDN link (domain mode) or deploy a new server
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

The SNI target is the domain that Reality impersonates. Choosing the wrong one can make the proxy detectable.

**Good SNI targets** (global CDN, shared hosting infrastructure):
- `www.microsoft.com` (default) — Azure CDN, global presence
- `www.twitch.tv` — Fastly CDN, global
- `dl.google.com` — Google CDN, global
- `github.com` — Fastly CDN, global

**Bad SNI targets** (proprietary ASN, instant detection):
- `apple.com`, `icloud.com` — Apple controls its own ASN ranges. If your VPS is on Hetzner/OVH/DigitalOcean and claims to be Apple, the ASN mismatch is immediately visible to censors.
- Small/niche websites — ASN inconsistencies are flagged instantly.

**Best practice:** Run `meridian scan` to find optimal SNI targets from the same network/datacenter as your server. This uses RealiTLScanner to discover nearby domains with valid TLS certificates.

## Interpreting `meridian check` Output

| Check | What It Tests | If It Fails |
|-------|--------------|-------------|
| SNI target reachability | Can the server reach the camouflage site (e.g., microsoft.com)? | Server's outbound is restricted. Try a different SNI target with `--sni` |
| SNI ASN match | Does the SNI target share a CDN/ASN with the server? | Use a global CDN domain (microsoft.com, twitch.tv, github.com). Avoid apple.com (Apple-owned ASN, instant detection) |
| Port 443 availability | Is port 443 free or used by Meridian? | Another service is on 443. Stop it or use a clean server |
| Port 443 external reachability | Can the outside world reach port 443? | Cloud firewall blocks it. Open port 443/TCP inbound |
| Domain DNS | Does the domain resolve to server IP? | Update DNS A record |
| Server OS | Is it Ubuntu/Debian? | Other distros may work but are untested |
| Disk space | At least 2GB free? | Free up space |

## Interpreting `meridian diagnostics` Output

| Section | What to Look For |
|---------|-----------------|
| Local Machine | Ansible version (needs 2.12+), OS compatibility |
| Server | OS version, uptime (recent reboot?), disk/memory usage |
| Docker | Is 3x-ui container running? Status should be "Up" |
| 3x-ui Logs | Error messages, "failed to start" entries, certificate issues |
| Listening Ports | Port 443 should show xray, haproxy, or 3x-ui. If missing, proxy isn't running |
| Firewall (UFW) | Port 443/tcp should be ALLOW. If not listed, it's blocked |
| SNI Target | Should show CONNECTED with a certificate chain. If unreachable, Reality can't work |
| Domain DNS | Should resolve to server IP. If different or empty, DNS is misconfigured |

## Interpreting `meridian ping` Output

| Check | Pass | Fail |
|-------|------|------|
| TCP port 443 | Server is network-reachable | Firewall, ISP block, or server down |
| TLS handshake | Reality protocol is working | Xray not running, port conflict, or SNI issue |
| Domain HTTPS | Caddy + HAProxy working | DNS, Caddy, or HAProxy issue |

**If all ping checks pass but VPN client still can't connect:**
- Re-scan the QR code or re-import the VLESS link
- Ensure device clock is accurate (within 30 seconds)
- Try a different VPN app (v2rayNG, Hiddify)
- Check that the app is using the Reality link, not an old/invalid one
