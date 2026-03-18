# Meridian

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/uburuntu/meridian)](https://github.com/uburuntu/meridian/stargazers)

One command deploys a censorship-resistant proxy server. Invisible to DPI, active probing, and TLS fingerprinting.

```bash
curl -sS https://raw.githubusercontent.com/uburuntu/meridian/main/setup.sh | bash
```

## How it works

Meridian deploys [VLESS+Reality](https://github.com/XTLS/Xray-core) — a protocol that makes your server indistinguishable from a legitimate website (e.g., microsoft.com):

- **Deep Packet Inspection** — traffic is byte-for-byte identical to normal HTTPS. No detectable proxy signatures.
- **Active probing** — censors that connect to your server get Microsoft's real TLS certificate back. Only clients with your private key reach the proxy.
- **TLS fingerprinting** — uTLS impersonates Chrome's exact Client Hello fingerprint, matching billions of real devices.

## What it does

The interactive wizard connects to your server via SSH and runs an Ansible playbook:

1. Installs Docker, deploys [Xray](https://github.com/XTLS/Xray-core) via [3x-ui](https://github.com/MHSanaei/3x-ui) panel
2. Generates x25519 keypair and unique credentials
3. Configures UFW firewall (ports 22 + 443), SSH key-only auth, BBR congestion control
4. Sets up VLESS+Reality on port 443
5. **With a domain:** adds HAProxy (SNI routing), Caddy (auto-TLS + decoy site), VLESS+WSS (CDN fallback via Cloudflare)
6. Outputs QR codes and saves an HTML page with connection links

## What you need

A Debian/Ubuntu VPS with root SSH key access. The script handles the rest.

## Modes

| Mode | What it does |
|------|-------------|
| **Standalone** | Single server, VLESS+Reality on port 443 |
| **Domain** | Adds decoy website, CDN fallback through Cloudflare, web panel access |
| **Chain** | Two-server relay for IP whitelist bypass (domestic relay + foreign exit) |

## Uninstall

```bash
curl -sS https://raw.githubusercontent.com/uburuntu/meridian/main/setup.sh | bash -s -- --uninstall
```

**Full docs:** [meridian.msu.rocks](https://meridian.msu.rocks)
