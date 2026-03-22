---
title: Domain Mode
description: Add CDN fallback via Cloudflare for IP-blocking resilience.
order: 4
section: guides
---

## What domain mode adds

Domain mode extends the standalone setup with three components:

1. **HAProxy SNI routing** — routes domain traffic to Caddy alongside Reality traffic to Xray
2. **Caddy TLS** — automatic Let's Encrypt certificates for your domain
3. **VLESS+WSS inbound** — CDN fallback through Cloudflare

The WSS connection routes through Cloudflare's CDN, making it work even if your server's IP is blocked — Cloudflare's IP ranges are too widely used to block.

## Deploy with domain

```
meridian deploy 1.2.3.4 --domain proxy.example.com
```

## Cloudflare setup

**Follow this exact order** to avoid TLS certificate issues:

1. Add your domain in Cloudflare, create an **A record** pointing to your server IP
2. Keep the cloud icon **grey** ("DNS only") — don't enable proxying yet
3. Run `meridian deploy` — Caddy obtains the TLS certificate automatically
4. Switch to **orange cloud** (Proxied)
5. Configure SSL/TLS → **Full (Strict)** and Network → **Enable WebSockets**

> **Important:** Caddy obtains certificates via HTTP-01 challenge on port 80. If Cloudflare's "Always Use HTTPS" is active, it breaks the challenge. Disable it or add a page rule for `/.well-known/acme-challenge/*`.

## Connection links

With domain mode, users get three connection options:

| Protocol | Priority | Route |
|----------|----------|-------|
| Reality | Primary | Direct to server IP |
| XHTTP | Alternative | Through Caddy on port 443 |
| WSS | Backup | Through Cloudflare CDN |

Users should try Reality first (fastest), XHTTP second, and WSS only if both fail (IP is blocked).
