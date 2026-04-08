---
title: Deploy Guide
description: Full deployment walkthrough with all configuration options.
order: 3
section: guides
---

This guide covers every deployment option. If you're deploying for the first time, start with [Getting Started](/docs/en/getting-started/) — it walks through the basics in five minutes.

## Basic deployment

```
meridian deploy 1.2.3.4
```

The wizard guides you through configuration. Or specify everything upfront:

```
meridian deploy 1.2.3.4 --sni www.microsoft.com --name alice --yes
```

## All flags

| Flag | Default | Description |
|------|---------|-------------|
| `--sni HOST` | www.microsoft.com | TLS camouflage target |
| `--domain DOMAIN` | (none) | Cloudflare CDN fallback domain |
| `--client-name NAME` | default | Name for the first client |
| `--display-name NAME` | (none) | Label for connection pages (e.g. "Alice's VPN") |
| `--icon EMOJI_OR_URL` | (none) | Page icon — emoji or image URL |
| `--color PALETTE` | ocean | Page color theme (ocean/sunset/forest/lavender/rose/slate) |
| `--user USER` | root | SSH user (non-root gets sudo automatically) |
| `--harden / --no-harden` | enabled | Harden SSH + firewall (disable with `--no-harden` if other services share the server) |
| `--server NAME` | | Target server (name or IP) |
| `--decoy MODE` | none | Decoy response for unknown paths (`none` / `403`) |
| `--yes` | | Skip confirmation prompts |

## Branding

Personalize connection pages so recipients know who set up their VPN:

```
meridian deploy 1.2.3.4 --server-name "Alice's VPN" --icon 🚀 --color sunset
```

- **`--server-name`** — appears in the trust bar and page title. Use your name or a friendly label.
- **`--icon`** — an emoji or image URL shown at the top of the connection page.
- **`--color`** — sets the accent color palette. Options: `ocean` (default), `sunset`, `forest`, `lavender`, `rose`, `slate`.

These settings are stored in server credentials and apply to all client connection pages.

## Choosing an SNI target

The SNI (Server Name Indication) target is the domain that Reality impersonates. The default (`www.microsoft.com`) works well for most cases.

For optimal stealth, scan your server's network for same-ASN targets:

```
meridian scan 1.2.3.4
```

**Good targets** (global CDN):
- `www.microsoft.com` — Azure CDN, global
- `www.twitch.tv` — Fastly CDN, global
- `dl.google.com` — Google CDN, global
- `github.com` — Fastly CDN, global

**Avoid** `apple.com` and `icloud.com` — Apple controls its own ASN ranges, making the IP/ASN mismatch instantly detectable.

## Pre-flight check

Not sure if your server is compatible?

```
meridian preflight 1.2.3.4
```

Tests SNI target reachability, ASN match, port availability, DNS, OS compatibility, and disk space — without installing anything.

## Re-running deploy

It's safe to re-run `meridian deploy` at any time. The provisioner is fully idempotent:
- Credentials are loaded from cache, not regenerated
- Steps check existing state before acting
- No duplicate work

## Non-root deployment

```
meridian deploy 1.2.3.4 --user ubuntu
```

Non-root users get `sudo` automatically. The user must have passwordless sudo access.

## Local deployment

If you're running Meridian directly on the server (e.g. logged in via SSH as root):

```
meridian deploy local
```

This skips SSH entirely and runs all commands locally. The `local` keyword works with all commands:

```
meridian client add alice local
meridian preflight local
meridian scan local
```

Useful when SSH to self doesn't work (missing keys, firewall rules), for re-deploying on the same server, or in cloud-init startup scripts.

## Adding a relay node

After deploying your exit server, add a relay node for resilience when the exit IP gets blocked. See the [Relay guide](/docs/en/relay/) for full setup instructions.

```bash
meridian relay deploy RELAY_IP --exit YOUR_EXIT_IP
```

## Management panel

Meridian deploys [3x-ui](https://github.com/MHSanaei/3x-ui) as the web management panel for Xray. You can access it directly in your browser to monitor traffic, view inbound configs, and check server status.

The panel URL and credentials are stored in your local credentials file:

```
cat ~/.meridian/credentials/<IP>/proxy.yml
```

The `panel` section contains everything you need:

```yaml
panel:
  username: a1b2c3d4e5f6
  password: Xk9mP2qR7vW4nL8jF3hT6yBs
  web_base_path: n7kx2m9qp4wj8vh3rf6tby5e
```

Open `https://<your-server-ip>/<web_base_path>/` in your browser and log in with the username and password.

The panel path is randomized for security — treat it like a password. All `meridian` CLI commands use this same panel API under the hood, so anything you can do in the CLI is also visible in the panel.

> **Note:** If you modify settings directly in the panel, they may be overwritten on the next `meridian deploy`.
