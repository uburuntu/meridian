# provision — Pure-Python step pipeline

## Design decisions

**Steps over monolithic script** — each step is a class with `run(conn, ctx) → StepResult` (ok/changed/skipped/failed). Composable, independently testable. Pipeline stops on first failure.

**Two pipelines**: `build_setup_steps()` for panel+node deploy, `build_node_steps()` for node-only. Both share OS/Docker steps, differ on panel deployment.

**Recipe graph** — builders wrap steps in `Operation` objects with explicit `requires`/`provides` resources. Add graph edges before relying on declaration order for new conditional chunks.

**Typed context** — `ProvisionContext` has typed fields for configuration AND typed properties for inter-step data (`ctx.panel_api`, `ctx.cluster`). Legacy `_state` dict kept for edge cases.

**Remnawave containers** — Panel (backend + PostgreSQL) in bridge network, node in host network. Panel on `127.0.0.1:3000`, reverse-proxied by nginx. The node container carries `cap_add: NET_ADMIN` — mandatory per upstream panel 2.6.2+ / 2.7.0+ docs. It enables the node plugin system (Torrent Blocker, Ingress/Egress Filter, Connection Drop) and the IP Control panel feature; without it operators can activate those features in the panel UI and see nothing happen (kernel EPERM on nftables syscalls, swallowed). System lab Stage 3 asserts the capability is present on the live container.

**Post-provisioner API setup** — Container deployment is SSH-based (provisioner steps). Panel/user/profile configuration happens via direct REST API calls AFTER containers are running. This separates infrastructure (SSH) from configuration (REST).

**nginx + TLS extracted** — `services.py` split into `nginx.py` (SNI routing + HTTP config) and `tls.py` (acme.sh cert issuance). Connection page deployment stays in `services.py`.

**Semantic ensure helpers** — `ensure.py` wraps package, file, service, and UFW operations. Prefer these helpers plus `ServerFacts` for idempotency checks instead of duplicating check/act shell snippets.

**Reporter hook** — `Provisioner.run()` may emit typed core events while preserving Rich rendering by default. CLI/UI renderers subscribe; steps still return `StepResult`.

**Relay pipeline is separate** — uses `RelayContext` and Realm TCP forwarding. Panel-agnostic.

## What's done well

- **Idempotent containers** — panel/node steps check `docker inspect` before deploying.
- **Health polling** — panel step waits for `/api/health`, node step waits for port binding.
- **Secret generation** — PostgreSQL password, JWT secrets generated per deploy via `secrets.token_hex`.

## Pitfalls

- **nginx `add_header` inheritance** — child `location` blocks with `add_header` suppress parent headers. Use `map` directives.
- **acme.sh shortlived IP certs** — 6-day certs need `--days 5` and explicit renew window.
- **nginx stream = dynamic module** — install `libnginx-mod-stream` package.
- **`return 444` is banned from HTTPS blocks** — use 403/404 instead (less fingerprintable).
- **Per-relay nginx files** — relay SNI routing uses per-file config, not monolithic rewrite.
- **Firewall must follow the effective sshd port** — never assume `22/tcp`.
- **Generated file content stays off shell commands** — use `conn.put_text()`/`put_bytes()` with mode/owner/sensitive flags, not heredocs or `printf`.
