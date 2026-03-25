# provision — Pure-Python provisioner

## Step pipeline

Steps are composable and independently testable. Each step returns a `StepResult` with status (success/skip/fail).

**Pipeline order:** common → docker → panel → xray inbounds → services (HAProxy/Caddy/connection page)

## Communication

Steps communicate via `ProvisionContext`:
- **Typed fields** for well-known data (IP, domain, credentials, etc.)
- **Dict-like access** (`ctx["key"]`) for ad-hoc inter-step data

`ProvisionContext` + `ServerConnection` are created by the CLI layer and passed into `build_setup_steps()`.

## Key patterns

- **Idempotent provisioning** — every step checks state before acting. Re-running `meridian deploy` on an already-provisioned server should be safe
- **Credential lockout prevention** — credentials saved locally BEFORE changing the panel password on the remote server. If the remote change fails, you still have access
- **Protocol-generic** — step pipeline loops over `PROTOCOLS` registry, no protocol-specific branches in pipeline assembly

## Adding a new step

1. Create step class with `run(ctx, conn)` method returning `StepResult`
2. Add to `build_setup_steps()` in correct pipeline position
3. Add unit test verifying both the action and the idempotent skip path
