# tests/realvm — Real-VM integration test harness

Provisions real cloud VMs (Hetzner via `hcloud-python`), deploys Meridian
against them, verifies, tears down. **Local-only — NEVER runs in CI.**
Costs real money (~€0.01 per full single-topology run).

## Design decisions

- **Never in CI** — `HCLOUD_TOKEN` is not a GitHub secret; harness files live outside `.github/workflows/`; `pyproject.toml` `norecursedirs = ["realvm"]` keeps `pytest` from collecting. Runs only via `make real-lab` locally.
- **Topology per YAML file** — `topologies/<name>.yml` declares provider / region / size / node list. `orchestrator.py` is the driver, verify scripts live in `verify/`. Easy to add new topologies (`chain-3hop`, `dual-ip`, `dual-stack-v6` land with their feature PRs).
- **Three-tier test structure** —
  - **Tier α**: fully automated (LE cert, UFW nmap, SSH pubkey-only, fail2ban, fleet status, client CRUD, plan cycle, subscription URL 200). Hard-pass required.
  - **Tier β**: env-gated semi-auto (`MERIDIAN_TEST_DOMAIN` + Cloudflare API). Skipped cleanly when unconfigured. Partially scaffolded; full wire-up tracked in #36.
  - **Tier γ**: interactive QR scan from phone. Gated on `MERIDIAN_TEST_INTERACTIVE=1`. Scaffold only today; tracked in #36.
- **Per-cloud SDK, no Terraform/Pulumi** — see `src/meridian/infra/CLAUDE.md` for rationale.
- **MERIDIAN_HOME isolation per fleet** — orchestrator sets `MERIDIAN_HOME=<fleet-id>/` before invoking `meridian deploy`, so the harness's cluster.yml doesn't clobber the developer's real `~/.meridian/`.

## What's done well

- **Safety rails**: `HCLOUD_TOKEN` env gate, cost estimate + `y/n` prompt, soft cap at 5 VMs, `try/finally` teardown in orchestrator, label-based orphan sweep via `make real-lab-orphans`.
- **Live-validated on Hetzner** — topology=single passes 13/0 (see PR #28 description).
- **Unbuffered output** via `PYTHONUNBUFFERED=1` in Makefile targets — real-time progress visible during long deploys.

## Pitfalls

- **Never put `HCLOUD_TOKEN` into GitHub Actions** — running real-VM tests from CI leaks budget silently when a workflow misbehaves.
- **Always teardown in `finally`** — the orchestrator does it; verify scripts must not hold the VM open on failure (except `--keep` explicitly).
- **Hetzner server types deprecate** — CX22 was deprecated in 2025; harness defaults to `cx23`. Refresh topology YAMLs and `providers/hetzner.py::_HOURLY_EUR` when upstream sunsets a generation.
- **Rich console ANSI in captured output** — `meridian fleet status` renders colors; prefer `meridian --json fleet status` in verify scripts for stable field access.

## Links

- Orchestrator: `orchestrator.py`
- Topology specs: `topologies/<name>.yml`
- Tier α verify: `verify/single.sh`
- README (user-facing): `README.md`
- Provider base: `src/meridian/infra/providers/base.py`
- Hetzner impl: `src/meridian/infra/providers/hetzner.py`
