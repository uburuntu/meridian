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
