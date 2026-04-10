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
- **Falsiness matters in `_extra`** — preserved forward-compat fields may legitimately be `false`, `0`, or `[]`. Only strip known empty-string placeholders; never drop unknown fields just because they are falsy.
- **Single QR warning** — warns once per session if `qrencode` missing, then silently degrades. No spam.

## Pitfalls

- **3x-ui API**: login is form-urlencoded (not JSON). `settings`/`streamSettings` must be JSON **strings** (Go quirk). Remove clients by UUID, not email.
- **Shell injection**: ALL `conn.run()` interpolated values MUST use `shlex.quote()`.
- **XHTTP dual mode**: no `xtls-rprx-vision` flow (must be empty string). Runs either with Reality (direct) or with `security: none` behind nginx TLS reverse proxy — two distinct stream settings paths.
- **`xray vlessenc` output changed**: newer Xray prints both X25519 and ML-KEM-768 sections with quoted `"decryption"`/`"encryption"` lines. Meridian's `--pq` path must pick the ML-KEM-768 pair, not the first section.
- **Local mode**: detection is file-based only — `/etc/meridian/proxy.yml` readable (root) or `/etc/meridian/` dir exists (non-root). Never use IP matching (`curl ifconfig.me`) — it false-positives when the user is connected via TUN mode (VPN) since their outbound IP matches the server.
- **Camouflage target**: never recommend apple.com (ASN mismatch with VPS providers).
- **WARP egress**: Cloudflare WARP client for server outbound routing. SOCKS5 on `127.0.0.1:40000`. CLI syntax varies between warp-cli versions (old: `set-mode proxy` vs new: `mode proxy`).
- **Post-quantum encryption**: ML-KEM-768 hybrid. When `decryption != "none"`, Xray fallbacks must be omitted — the two features are mutually exclusive in stream settings.
