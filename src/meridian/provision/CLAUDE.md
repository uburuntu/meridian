# provision — Pure-Python step pipeline

## Design decisions

**Steps over monolithic script** — each step is a class with `run(conn, ctx) → StepResult` (ok/changed/skipped/failed). Composable, independently testable. Pipeline stops on first failure.

**Order matters**: packages → Docker → panel config → Xray inbounds → HAProxy → Caddy → connection page. Each step depends on artifacts from earlier steps.

**Hybrid context** — `ProvisionContext` has typed fields for configuration (IP, domain, ports) and a dict for inter-step data (panel client, UUIDs). Typed fields are self-documenting; dict keeps steps loosely coupled.

**Idempotency by convention** — every step checks state before acting. Re-running `deploy` on a configured server is fast and safe.

**Protocol-generic assembly** — `build_setup_steps()` loops over `PROTOCOLS` registry. Adding a protocol doesn't require editing pipeline code.

## What's done well

- **Credential lockout prevention** — save locally BEFORE changing remote password. If API fails, user has recovery data.
- **`deployed_with` updated on re-deploy** — not just fresh deploys. Enables downstream version mismatch warnings.

## Pitfalls

- **JSON string quirk** — 3x-ui API requires `settings`/`streamSettings` as JSON *strings*, not objects. Tests verify this explicitly.
- **HAProxy SNI catch-all** — unrecognized SNIs drop silently. Intentional anti-fingerprinting, surprising when debugging.
- **Realm hash verification** — SHA256 mismatch = hard failure. This is supply chain defense, not a bug.
