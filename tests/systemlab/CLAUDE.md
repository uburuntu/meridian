# tests/systemlab — Multi-node system validation lab

```bash
make system-lab               # ~5 min (cached images), ~15 min (cold)
# or manually:
bash tests/systemlab/scripts/setup-fixtures.sh
docker compose -f tests/systemlab/compose.yml up --build \
  --abort-on-container-exit --exit-code-from controller
docker compose -f tests/systemlab/compose.yml down -v
```

## What is tested

The system lab deploys Meridian across two containers via SSH — exactly like a real VPS — and verifies the full lifecycle with real Remnawave containers.

### 8 test stages

| # | Stage | What it validates |
|---|-------|-------------------|
| 1 | SSH/systemd setup | Host key scanning, systemd boot, Pebble CA install |
| 2 | Fresh deploy | Full provisioner pipeline: Docker, Remnawave panel+DB+Valkey+node, nginx, TLS |
| 3 | Verify deployment | 4 containers running, nginx valid, port 443, cluster.yml, fleet status connected |
| 4 | Client lifecycle | add/list/show/remove via panel API |
| 5 | Relay deploy | Realm install, systemd service, relay host entries in panel |
| 6 | Connection test | Reality tunnel through xray client (direct + via relay) |
| 7 | Redeploy | Key preservation — Reality keys unchanged, existing clients still work |
| 8 | Teardown | Container removal, port freed, nginx cleaned |

## Design decisions

**Real systemd, real SSH** — containers run `/sbin/init`, services managed by real unit files. No mocked systemctl.

**Nested Docker daemon** — exit node runs its own `dockerd` (vfs driver, no iptables). Remnawave images pulled inside this nested daemon, exactly like production.

**Static IPs** — deterministic `172.30.0.0/24` bridge. SSH known_hosts, credential paths, and deploy commands are stable.

**Fixtures generated at runtime** — SSH keypair and Pebble CA created by `setup-fixtures.sh`, never committed.

## Pitfalls

- **xray `geoip:private` blocks lab IPs** — can't use internal echo service. Test uses ifconfig.me (external).
- **Pebble can't issue IP certs** — ACME protocol limitation. Infrastructure ready; needs domain mode (phase 2).
- **Image pull time** — 4 Remnawave images (~500MB) pulled inside nested Docker on first run. Expect 3-5 min in CI.
- **systemd reports `degraded`** — some kernel features missing in containers. Accepted.
- **Base image build is slow** — docker-ce from official repo. Uses BuildKit apt cache mounts.
