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
meridian deploy [IP|local] [flags]     Deploy proxy server ('local' = on this server, no SSH)
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
