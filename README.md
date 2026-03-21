<p align="center">
  <img src="docs/img/logo-512.png" width="80" alt="Meridian">
</p>

<h1 align="center">Meridian</h1>

<p align="center">
  <a href="https://github.com/uburuntu/meridian/actions/workflows/ci.yml"><img src="https://github.com/uburuntu/meridian/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/meridian-vpn/"><img src="https://img.shields.io/pypi/v/meridian-vpn" alt="PyPI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://github.com/uburuntu/meridian/stargazers"><img src="https://img.shields.io/github/stars/uburuntu/meridian" alt="GitHub stars"></a>
</p>

<p align="center">Deploy a censorship-resistant proxy server in one command.<br>Invisible to DPI, active probing, and TLS fingerprinting.</p>

<p align="center">
  <img src="docs/img/connection-page.png" width="720" alt="Connection page with QR codes">
</p>

## What is this

Meridian deploys a private, undetectable VPN server in minutes. Share secure internet access with family and friends — they scan a QR code and connect. When your IP gets blocked, spin up a new server and be back online in minutes. No technical knowledge required on the client side.

Whether you're the "tech friend" setting up VPN for people you care about, a power user managing multiple servers, or an NGO providing access in a censored region — Meridian handles the complexity so you can focus on staying connected.

See [SECURITY.md](SECURITY.md) for the threat model and what Meridian protects against (and what it doesn't).

## Install

Works on **macOS and Linux**. Windows users: use WSL.

```bash
curl -sSf https://meridian.msu.rocks/install.sh | bash
```

Or install directly from PyPI:

```bash
uv tool install meridian-vpn    # recommended
pipx install meridian-vpn       # alternative
```

## Quick start

```bash
meridian setup                       # interactive wizard
meridian setup 1.2.3.4               # deploy to server
meridian setup 1.2.3.4 --domain d.io # with CDN fallback
```

After setup, your server is a fully functional proxy. Share access:

```bash
meridian client add alice            # generate keys for a friend
meridian client list                 # see all clients
meridian client remove alice         # revoke access
```

Each client gets an HTML page with QR codes and one-tap deep links. In domain mode, the page is also hosted on the server with [live usage stats](https://meridian.msu.rocks/demo).

## How it works

Meridian deploys [VLESS+Reality](https://github.com/XTLS/Xray-core) — a protocol that makes your server indistinguishable from a legitimate website:

| Censorship method | How Meridian beats it |
|---|---|
| **Deep Packet Inspection** | Traffic is byte-for-byte identical to normal HTTPS. No proxy signatures. |
| **Active probing** | Censors connecting to your server get a real TLS certificate from microsoft.com. Only clients with your private key reach the proxy. |
| **TLS fingerprinting** | uTLS impersonates Chrome's exact Client Hello, matching billions of real devices. |
| **IP blocking** | Domain mode routes through Cloudflare CDN as a fallback — no direct IP exposure. |

## What you need

- A VPS (Debian/Ubuntu) with root SSH key access — $3–5/month from any provider
- Recommended: Finland, Netherlands, Sweden, Germany (low latency, not flagged)
- Optional: a domain pointed to the server (for CDN fallback via Cloudflare)

## Commands

| Command | Description |
|---------|-------------|
| `meridian setup [IP]` | Deploy proxy server (interactive wizard if no IP) |
| `meridian setup IP --xhttp` | Deploy with XHTTP transport (enhanced stealth) |
| `meridian client add NAME` | Add a named client key |
| `meridian client list` | List all clients |
| `meridian client remove NAME` | Remove a client key |
| `meridian server list` | List managed servers |
| `meridian check [IP]` | Pre-flight validation (ports, SNI, ASN, DNS) |
| `meridian scan [IP]` | Find optimal SNI targets on server's network |
| `meridian ping [IP]` | Test proxy reachability from this device |
| `meridian diagnostics [IP]` | Collect info for bug reports |
| `meridian uninstall [IP]` | Remove proxy from server |
| `meridian self-update` | Update CLI |

## Architecture

<img src="docs/img/architecture.png" width="720" alt="Meridian architecture">

**Standalone mode** — Xray on port 443. No domain needed.

**Domain mode** — HAProxy routes by SNI: Reality traffic goes to Xray, everything else to Caddy (auto-TLS). Adds VLESS+WSS through Cloudflare CDN as a fallback.

## Client apps

After setup, connect with any of these apps:

| Platform | App |
|----------|-----|
| iOS | [v2RayTun](https://apps.apple.com/app/v2raytun/id6476628951) |
| Android | [v2rayNG](https://github.com/2dust/v2rayNG/releases/latest) |
| Windows | [v2rayN](https://github.com/2dust/v2rayN/releases/latest) |
| All platforms | [Hiddify](https://github.com/hiddify/hiddify-app/releases/latest) |

## Common scenarios

**My IP got blocked** — The most common scenario in censored regions. Get a new VPS, run `meridian setup NEW_IP`, then re-add clients with `meridian client add`. If you're in domain mode, update the DNS A record to point at the new IP and re-run setup. If you're not using domain mode yet, consider switching (`--domain`) to get a CDN fallback through Cloudflare — when the IP is blocked, the WSS/CDN link still works.

**Sharing with family** — After `meridian client add alice`, you get an HTML file. Send it by email, iMessage, or AirDrop. They open it on their phone, install the app (one tap), scan the QR code, and connect. In domain mode, the page is also hosted at a URL (`https://yourdomain/connection`) you can share as a link — no file transfer needed.

**First-time VPS setup** — Rent a VPS from any provider (DigitalOcean, Hetzner, Vultr — $4–6/month). Choose Debian 12 or Ubuntu 22.04+. Make sure you have SSH key access (not just password). Then run `meridian setup YOUR_SERVER_IP`.

## Troubleshooting

Not connecting? Run `meridian ping` to check if the server is reachable, or use the [web-based ping tool](https://meridian.msu.rocks/ping).

Something else not working? Get instant AI-powered help:

```bash
meridian diagnostics --ai        # copies an AI-ready prompt to clipboard
```

Paste the prompt into ChatGPT, Claude, or any AI assistant for personalized troubleshooting.

Or [open an issue](https://github.com/uburuntu/meridian/issues) with `meridian diagnostics` output.

## Docs

Full documentation, interactive command builder, and setup guides:

**[meridian.msu.rocks](https://meridian.msu.rocks)** · [Connection page demo](https://meridian.msu.rocks/demo)
