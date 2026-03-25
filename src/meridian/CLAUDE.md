# src/meridian — Python CLI package

## Key API patterns

- **3x-ui login**: `POST /login` with form-urlencoded (NOT JSON)
- **Add inbound**: `POST /panel/api/inbounds/add` — `settings`, `streamSettings`, `sniffing` must be JSON **strings** (Go struct quirk)
- **Remove client** by UUID (not email — email silently succeeds but doesn't delete)

## Protocol conventions

- XHTTP doesn't support `xtls-rprx-vision` flow (must be empty string)
- XHTTP behind Caddy: internal port only, `security: tls`, path-based routing
- `reality_dest` derived from `reality_sni` (`{sni}:443`)
- **Camouflage target**: never recommend apple.com (ASN mismatch). Best: run `meridian scan` for same-network targets
- HAProxy: do NOT use `check` on TLS backends

## Relay conventions

- **L4 transparent** — dumb TCP forwarder, never terminates or inspects TLS
- **All protocols work through relay** — Reality (end-to-end), XHTTP/WSS (with explicit `sni=exit_ip_or_domain`)
- **Realm version pinned** in `config.py` (REALM_VERSION), downloaded from GitHub releases
- **Same-server relay+exit** supported for testing (must use `--port` != 443)
- **Relay credentials** stored on exit server's `proxy.yml` (relays section) + `/etc/meridian/relay.yml` on relay
- **Connection pages auto-regenerated** when relay topology changes (deploy/remove)

## Local deployment conventions

- **`local` keyword** accepted wherever an IP is expected: `meridian deploy local`, `meridian check local`
- **Also accepts `locally`** — case-insensitive (`Local`, `LOCAL`, `Locally`)
- Handled in `resolve.py`: `is_local_keyword()` + `detect_public_ip()`
- Sets `local_mode=True` on `ServerConnection` — commands execute via `bash -c` instead of SSH
- `LOCAL_KEYWORDS = ("local", "locally")` canonical tuple in `resolve.py`

## CLI conventions

- `console.fail()` raises `typer.Exit(1)`. Always include `hint_type` and action items
- `VERSION` file is single source of truth. CI validates format
- Auto-update: auto-patches, prompts for minor/major

## Credential flow

- **V2 format**: nested YAML with `version: 2`, sections: `panel`, `server`, `protocols`, `clients`, `relays`
- Server source of truth: `/etc/meridian/proxy.yml`. Local cache: `~/.meridian/credentials/<IP>/proxy.yml`
- CLI fetches from server via SSH when not found locally
- Relay nodes store `/etc/meridian/relay.yml` (role, exit IP, ports)

## Protocol/inbound type registry

- `protocols.py` — `INBOUND_TYPES` dict + `PROTOCOLS` ordered dict — sole source of truth
- Adding a new protocol: add `InboundType`, create `Protocol` subclass, append to `PROTOCOLS`, add provisioner step

## CLI ↔ provisioner relationship

- CLI creates `ProvisionContext` + `ServerConnection`. `build_setup_steps()` assembles the step pipeline
- Pipeline: common → docker → panel → xray inbounds → services (HAProxy/Caddy/connection page)
- Steps communicate via `ProvisionContext` typed fields + dict-like access
