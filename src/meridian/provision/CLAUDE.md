# provision — Pure-Python step pipeline

## Design decisions

**Steps over monolithic script** — each step is a class with `run(conn, ctx) → StepResult` (ok/changed/skipped/failed). Composable, independently testable. Pipeline stops on first failure.

**Order matters**: packages → Docker → panel config → Xray inbounds → nginx → connection page. Each step depends on artifacts from earlier steps.

**Hybrid context** — `ProvisionContext` has typed fields for configuration (IP, domain, ports) and a dict for inter-step data (panel client, UUIDs). Typed fields are self-documenting; dict keeps steps loosely coupled.

**Idempotency by convention** — every step checks state before acting. Re-running `deploy` on a configured server is fast and safe.

**Protocol-generic assembly** — `build_setup_steps()` loops over `PROTOCOLS` registry. Adding a protocol doesn't require editing pipeline code.

## What's done well

- **Credential lockout prevention** — save locally BEFORE changing remote password. If API fails, user has recovery data.
- **`deployed_with` updated on re-deploy** — not just fresh deploys. Enables downstream version mismatch warnings.
- **nginx = genuine identity** — the server IS nginx. No decoy headers, no fingerprinting leaks. `server_tokens off` is all that's needed.

## Pitfalls

- **JSON string quirk** — 3x-ui API requires `settings`/`streamSettings` as JSON *strings*, not objects. Tests verify this explicitly.
- **nginx SNI catch-all** — all unrecognized SNIs route to nginx_https (same response as direct IP). This eliminates the routing differential that a blackhole (RST vs certificate) would create — censors see identical behavior regardless of SNI.
- **Realm hash verification** — SHA256 mismatch = hard failure. This is supply chain defense, not a bug.
- **nginx `add_header` inheritance** — child `location` blocks with `add_header` suppress parent headers entirely. Use `map` directives for variable headers to avoid duplication.
- **acme.sh bootstrap** — nginx needs a cert to start SSL, but acme.sh needs nginx on port 80. Solution: self-signed bootstrap cert, then issue real cert, then reload.
- **acme.sh empty email** — `email=''` breaks the installer (`shift` error). Omit the arg when no email: `sh -s --` not `sh -s email=''`.
- **nginx.conf stream block** — the default nginx.conf only has `http {}`. The stream block for SNI routing must be injected at the top level. Check idempotently before inserting.
- **nginx stream = dynamic module** — on Ubuntu, stream is compiled as dynamic (`--with-stream=dynamic`). `nginx -V` shows compile flags but the `.so` isn't installed until `libnginx-mod-stream` is installed. Always install the package, don't trust compile flags.
- **`return 444` is the default** — silent drop (send nothing, close connection). `--decoy 403` uses realistic nginx error codes: root returns 403 (directory listing forbidden), other paths return 404 (not found). This matches genuine nginx with an empty document root. 444 mode uses uniform 444 across both location blocks.
- **HTTP/2 on listen** — must add `http2` to the `listen` directive. Without it, ALPN only negotiates HTTP/1.1 — a fingerprinting vector since all modern servers support h2.
- **Port 443 allowed list** — `docker.py` and `setup.py` both check port 443 occupancy. Both must include `haproxy`/`caddy` for upgrade-from-old-stack to work.
- **Step constructor defaults must be `None` for context-resolved fields** — `InstallNginx` uses `None` defaults with `if x is not None else ctx.Y` resolution. Never use truthy defaults (like `10443` or `DEFAULT_PANEL_PORT`) for fields that fall back to context — they silently mask the fallback. Fixed defaults (like `nginx_internal_port=8443`) that are never resolved from context are fine as-is.
- **Xray `listen` field** — omitting `listen` from 3x-ui API defaults to all interfaces. When nginx fronts Xray, set `"listen": "127.0.0.1"`.
