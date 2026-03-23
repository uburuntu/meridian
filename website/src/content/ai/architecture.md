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
