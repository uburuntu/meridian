# src/meridian — Python CLI package

## Design decisions

**Protocol registry** — `protocols.py` defines `PROTOCOLS` as the sole source of truth. `ProtocolKey(StrEnum)` in `cluster.py` provides type-safe keys. All URL building, rendering, and provisioning loop over this registry.

**Cluster config** — Single `cluster.yml` at `~/.meridian/cluster.yml` replaces per-server `proxy.yml` files. Client/user state lives in Remnawave's PostgreSQL, not locally. Only deployment topology (panel URL, API token, nodes, relays) is stored locally.

**Remnawave integration** — `remnawave.py` wraps the REST API with `httpx`. Direct HTTPS calls from deployer's machine (no SSH tunneling for API). JWT auth, retry with backoff, Meridian-specific error types.

**SSH abstraction** — `ServerConnection` unifies local and remote execution. Local mode uses `bash -c`; remote uses SSH. Non-root triggers `sudo -n`.

**Console output** — `fail()` with `hint_type` (user/system/bug) controls the footer. Every error must be actionable.

## What's done well

- **Forward-compatible YAML** — `_extra` dict in ClusterConfig means newer versions don't corrupt older CLI reads.
- **Single source of state** — No split-brain. Remnawave DB is authoritative for users. cluster.yml is authoritative for deployment topology. No sync needed.
- **Relay = Host** — Relays map to Remnawave Host entries. Enable/disable host → subscriptions auto-adapt.

## Pitfalls

- **Shell injection**: ALL `conn.run()` interpolated values MUST use `shlex.quote()`.
- **ProtocolKey is StrEnum** — works as dict key but YAML serialization needs `_stringify_keys()` to avoid Python-tagged output.
- **Panel accessible via HTTPS** — unlike 3x-ui (SSH curl), Remnawave panel is reverse-proxied by nginx on a secret path. Direct REST calls from deployer machine.
- **Local mode**: detection is file-based only — `/etc/meridian/node.yml` or dir existence.
- **Camouflage target**: never recommend apple.com (ASN mismatch with VPS providers).
