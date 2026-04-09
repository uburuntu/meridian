# tests/e2e — End-to-end deployment tests

## What E2E tests vs unit tests

Unit tests verify components in isolation with mocks. E2E tests run `meridian deploy` against a real Docker container with sshd, verifying the full lifecycle. This is a **shell script** (`run-e2e.sh`), not pytest.

## How it works

- Container has sshd on port 2222; meridian SSHs to `127.0.0.1`
- Docker socket mounted; provisioner creates 3x-ui on the host daemon
- Dockerfile pre-installs all required packages so provisioner steps mostly skip
- Mock `systemctl` and acme.sh stub (returns rc=2 to skip cert generation)
- Stages: prerequisites → fresh deploy → verify → idempotent re-run → client CRUD → test → preflight → doctor → teardown (with cron cleanup verification) → re-deploy after teardown

## What's done well

- **Non-fatal graceful handling** — idempotent re-run and re-deploy after teardown accept Docker PID namespace failures without failing the overall run.
- **Cron cleanup verification** — catches the v3.3.1 regression where `update-stats` cron jobs survived teardown.

## Pitfalls

- **`ss -tlnp` fails across PID namespaces** — can't resolve process names in Docker. Port checks may false-negative. Accepted limitation.
- **15min CI timeout** — provisioning is slow. Hung Docker step stalls the entire job.
- **Teardown removes meridian binary** — `pip install --force-reinstall` needed before re-deploy stage.
- **Ephemeral state** — container is fresh each CI run. No persistent state debugging.
