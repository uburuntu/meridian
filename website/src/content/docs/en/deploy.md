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
