# Meridian

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/uburuntu/meridian)](https://github.com/uburuntu/meridian/stargazers)

Deploy a censorship-resistant proxy server in one command. Invisible to DPI, active probing, and TLS fingerprinting.

## Install

```bash
curl -sSf https://meridian.msu.rocks/install.sh | bash
```

## Quick start

```bash
meridian setup                       # interactive wizard
meridian setup 1.2.3.4               # deploy to server
meridian setup 1.2.3.4 --domain d.io # with decoy website + CDN fallback
```

After setup, your server is a fully functional proxy. Share access:

```bash
meridian client add alice            # generate keys for a friend
meridian client list                 # see all clients
meridian client remove alice         # revoke access
```

## How it works

Meridian deploys [VLESS+Reality](https://github.com/XTLS/Xray-core) — a protocol that makes your server indistinguishable from a legitimate website:

| Censorship method | How Meridian beats it |
|---|---|
| **Deep Packet Inspection** | Traffic is byte-for-byte identical to normal HTTPS. No proxy signatures. |
| **Active probing** | Censors connecting to your server get a real TLS certificate from microsoft.com. Only clients with your private key reach the proxy. |
| **TLS fingerprinting** | uTLS impersonates Chrome's exact Client Hello, matching billions of real devices. |
| **IP blocking** | Domain mode routes through Cloudflare CDN as a fallback — no direct IP exposure. |

## What you need

A VPS (Debian/Ubuntu) with root SSH key access. $3–5/month from any provider. Meridian handles the rest.

## Commands

| Command | Description |
|---------|-------------|
| `meridian setup [IP]` | Deploy proxy server (interactive wizard if no IP) |
| `meridian client add NAME` | Add a named client key |
| `meridian client list` | List all clients |
| `meridian client remove NAME` | Remove a client key |
| `meridian server list` | List managed servers |
| `meridian check [IP]` | Pre-flight validation |
| `meridian diagnostics [IP]` | Collect info for bug reports |
| `meridian uninstall [IP]` | Remove proxy from server |
| `meridian self-update` | Update CLI |

## Architecture

```
                     ┌─────────────────────────────┐
                     │         Your Server          │
                     │                              │
  User ───443───►    │  HAProxy (SNI routing)       │
                     │    ├─► Xray (VLESS+Reality)  │
                     │    ├─► Caddy (decoy site)    │
                     │    └─► Caddy (VLESS+WSS)     │
                     │                              │
  Censor ──probe──►  │  → sees microsoft.com TLS ✓  │
                     └─────────────────────────────┘
```

**Standalone mode** — Xray on port 443. No domain needed.

**Domain mode** — HAProxy routes by SNI: Reality traffic goes to Xray, everything else to Caddy (auto-TLS + decoy site). Adds VLESS+WSS through Cloudflare CDN as a fallback.

**Chain mode** — Two servers: a relay on a whitelisted IP (e.g., Russia) forwards to an exit node abroad via VLESS+Reality+XHTTP.

## Docs

Full documentation, interactive command builder, and client app links:

**[meridian.msu.rocks](https://meridian.msu.rocks)**

## Feedback

Something not working? Run `meridian diagnostics` and [open an issue](https://github.com/uburuntu/meridian/issues).
