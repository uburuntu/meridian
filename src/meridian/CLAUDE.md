# src/meridian — Python CLI package

## Design decisions

**Protocol registry** — `protocols.py` defines `INBOUND_TYPES` + `PROTOCOLS` as the sole source of truth. All URL building, rendering, and provisioning loop over this registry. Adding a protocol means adding a dataclass + `Protocol` subclass — everything else picks it up automatically.

**Credentials versioning** — V2 nested YAML with `_extra` dict for forward-compatibility. Unknown fields are preserved on load and re-emitted on save. V1 flat format auto-migrates. Atomic writes via tempfile+rename with `0o600` permissions.

**SSH abstraction** — `ServerConnection` unifies local and remote execution. Local mode uses `bash -c`; remote uses SSH. Non-root triggers `sudo -n`. This single abstraction lets every command work identically on-server and remotely.

**Console output** — `fail()` with `hint_type` (user/system/bug) controls the footer: no link for input errors, suggests `doctor` for infrastructure, shows GitHub for bugs. Every error must be actionable.

**Panel client** — Wraps 3x-ui REST API via SSH curl. Session cookies in `$HOME/.meridian/.cookie`. Short-lived: create, use, close.

## What's done well

- **Credential lockout prevention** — save locally BEFORE changing remote password. If API fails, user has recovery data.
- **Forward-compatible YAML** — `_extra` dict means newer server versions don't corrupt older CLI reads.
- **Single QR warning** — warns once per session if `qrencode` missing, then silently degrades. No spam.

## Pitfalls

- **3x-ui API**: login is form-urlencoded (not JSON). `settings`/`streamSettings` must be JSON **strings** (Go quirk). Remove clients by UUID, not email.
- **Shell injection**: ALL `conn.run()` interpolated values MUST use `shlex.quote()`.
- **XHTTP**: no `xtls-rprx-vision` flow (must be empty string). Requires Caddy TLS reverse proxy.
- **HAProxy**: never use `check` on TLS backends (breaks Reality handshake).
- **Local mode**: IP detection via `curl ifconfig.me` fails in air-gapped networks. File check on `/etc/meridian/proxy.yml` is the fallback.
- **Camouflage target**: never recommend apple.com (ASN mismatch with VPS providers).
