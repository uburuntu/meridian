---
title: Deploy Guide
description: Full deployment walkthrough with all configuration options.
order: 3
section: guides
---

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
| `--sni HOST` | www.microsoft.com | Site that Reality impersonates |
| `--domain DOMAIN` | (none) | Enable domain mode with CDN fallback |
| `--email EMAIL` | (none) | Email for TLS certificates (optional) |
| `--xhttp / --no-xhttp` | enabled | XHTTP transport (through port 443 via Caddy) |
| `--name NAME` | default | Name for the first client |
| `--user USER` | root | SSH user (non-root gets sudo automatically) |
| `--yes` | | Skip confirmation prompts |

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
meridian check local
meridian scan local
```

Useful when SSH to self doesn't work (missing keys, firewall rules), for re-deploying on the same server, or in cloud-init startup scripts.

## Adding a relay node

After deploying your exit server, you can add a relay node for resilience. A relay is a lightweight TCP forwarder on a domestic server that routes traffic to your exit server abroad — useful when the exit IP gets blocked.

```bash
meridian relay deploy RELAY_IP --exit YOUR_EXIT_IP
```

Clients automatically receive relay URLs when you add or update their connection pages. See the [CLI reference](/docs/en/cli-reference/) for all relay commands.
