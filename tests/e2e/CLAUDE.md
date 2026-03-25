# tests/e2e — End-to-end deployment tests

## What E2E tests vs unit tests

Unit tests verify components in isolation with mocks. E2E tests run `meridian deploy` against a real Docker container with sshd, verifying the full lifecycle: install → configure → verify → re-deploy (idempotency).

## How it works

- Container has sshd on port 2222; meridian SSHs to `127.0.0.1`
- Docker socket mounted; provisioner creates 3x-ui on the host daemon
- Five stages: prerequisites → fresh deploy → verify → idempotent re-run → client management

## Pitfalls

- **`ss -tlnp` fails across PID namespaces** — can't resolve process names in Docker. Port checks may false-negative. Accepted limitation.
- **15min CI timeout** — provisioning is slow. Hung Docker step stalls the entire job.
- **Ephemeral state** — container is fresh each CI run. No persistent state debugging.
