---
title: Security
description: Security design, vulnerability reporting, and scope.
order: 11
section: reference
---

## Reporting vulnerabilities

If you discover a security vulnerability in Meridian:

1. **Do NOT open a public issue**
2. Email the maintainer or use [GitHub Security Advisories](https://github.com/uburuntu/meridian/security/advisories/new)
3. Include steps to reproduce and potential impact

We aim to respond within 48 hours and will credit reporters in the fix.

## Security design

- **Credentials**: stored with `0600` permissions, secrets never passed through shell commands without `shlex.quote()`, redacted from `meridian doctor` output
- **Panel access**: reverse-proxied by nginx at a secret HTTPS path in all modes — no SSH tunnel required. Panel URL and credentials are in `~/.meridian/credentials/<IP>/proxy.yml`
- **SSH**: password authentication disabled by default
- **Firewall**: UFW configured with deny-all-incoming, only ports 22, 80, and 443 opened
- **Docker**: 3x-ui image pinned to a tested version
- **TLS**: acme.sh handles certificates via Let's Encrypt, served by nginx

## Scope

Meridian configures proxy servers — it does **not** implement cryptographic protocols. The underlying security depends on:

- [Xray-core](https://github.com/XTLS/Xray-core) — VLESS+Reality protocol
- [3x-ui](https://github.com/MHSanaei/3x-ui) — management panel
- [nginx](https://nginx.org/) — SNI routing and TLS termination
