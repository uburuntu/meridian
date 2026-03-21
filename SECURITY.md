# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Meridian, please report it responsibly:

1. **Do NOT open a public issue** for security vulnerabilities
2. Email the maintainer or use [GitHub Security Advisories](https://github.com/uburuntu/meridian/security/advisories/new)
3. Include steps to reproduce and potential impact

We aim to respond within 48 hours and will credit reporters in the fix.

## Security Design

- **Credentials**: stored locally with `0600` permissions, secrets are never passed through shell command strings without `shlex.quote()` and are redacted from `meridian diagnostics` output
- **Panel access**: bound to `127.0.0.1` (SSH tunnel required in no-domain mode)
- **SSH**: password authentication disabled by default
- **Firewall**: UFW configured with deny-all-incoming, only ports 22 + 443 (+ 80 for ACME)
- **Docker image**: pinned to a tested version to prevent supply chain issues
- **TLS**: Caddy handles certificates automatically via Let's Encrypt

## Scope

This project configures proxy servers — it does NOT implement cryptographic protocols. The underlying security depends on [Xray-core](https://github.com/XTLS/Xray-core), [3x-ui](https://github.com/MHSanaei/3x-ui), [Caddy](https://github.com/caddyserver/caddy), and [HAProxy](https://www.haproxy.org/).
