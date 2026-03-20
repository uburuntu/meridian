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
  --name NAME                   Server display name
  --user USER                   SSH user (default: root)
  --yes                         Skip confirmation prompts

meridian client add|list|remove NAME    Manage client access keys
meridian server add|list|remove         Manage known servers
meridian check [IP] [--ai]              Pre-flight server validation
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
