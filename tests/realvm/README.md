# Real-VM test harness

**Local-only.** Provisions actual cloud VMs (Hetzner today), runs Meridian
deploy + verification against them, then tears down. Complements the Docker
system-lab by covering things Docker cannot — real Let's Encrypt certs, real
UFW packet filtering, real SSH hardening, real xray egress behaviour.

**Costs real money.** A full single-node run takes ~5-10 minutes, which at
Hetzner CX22 pricing is about €0.001 — essentially free for an occasional
validation, but it IS money leaving your account, and a bug (or forgotten
`--keep`) could leave a VM running. The harness has safety rails but no
substitute for paying attention.

> ⚠️ This harness **never runs in CI**. `HCLOUD_TOKEN` is never a GitHub
> Actions secret. Running cloud tests from CI is how budgets silently bleed;
> manual operation is intentional.

## Quick start

```bash
# 1. Install the optional Hetzner dependency
uv sync --extra hetzner

# 2. Get a Hetzner API token
#    https://console.hetzner.cloud → Project → Security → API Tokens
#    Permission: Read & Write
export HCLOUD_TOKEN=<your-token>

# 3. Run the baseline topology
make real-lab
# (confirms cost, provisions, verifies, destroys)
```

That's it. On success you'll see `PASS: N  FAIL: 0` and the VM will be gone.

## Topologies

Topology files live in `tests/realvm/topologies/*.yml`.

| Name | VMs | What it validates |
|---|---|---|
| `single` | 1 | Baseline — LE cert, UFW, SSH, fleet status, client CRUD, declarative apply, subscription URL |
| (future) `chain-2hop` | 2 | Domestic relay → foreign exit (tests chain correctness) |
| (future) `chain-3hop` | 3 | Full chain — client → ingress → middle → exit |
| (future) `dual-ip` | 1 | Node with 2 Primary IPs (ingress IP ≠ egress IP) |
| (future) `dual-stack-v6` | 1 | IPv4 ingress + IPv6 egress |

Run a non-default topology:

```bash
make real-lab TOPO=single
```

## Test tiers

**Tier α — fully automated.** Runs by default. No user involvement.

- LE cert chain validates against real CA
- External port scan: only 22/80/443 open
- SSH password auth refused after hardened redeploy
- fail2ban active
- `meridian fleet status` reports green
- Client add/list/remove round-trip via real panel API
- `meridian plan` exits 0 or 2 (converged or changes pending — both OK)
- Subscription URL returns HTTP 200 with xray-shaped body

**Tier β — semi-automated.** Runs if you provide extra env vars. Skipped
otherwise with a clear log line.

| Env var | Enables |
|---|---|
| `MERIDIAN_TEST_DOMAIN=vpn.example.com` | Domain mode + real LE cert for the domain |
| `CLOUDFLARE_API_TOKEN=...` + `CLOUDFLARE_ZONE_ID=...` | Cloudflare DNS automation + CDN path tests |
| `MERIDIAN_TEST_SSH_KEY=/path/to/custom.pub` | Use your own SSH key (otherwise `~/.ssh/id_ed25519.pub`) |

**Tier γ — interactive.** Triggered by `TIER=interactive` or
`MERIDIAN_TEST_INTERACTIVE=1`. Harness keeps VMs alive and prompts you to
verify from a second device (phone, browser in another region) before
destroying.

```bash
MERIDIAN_TEST_INTERACTIVE=1 make real-lab-keep TOPO=single
# ... harness provisions, prints QR code + subscription URL ...
# ... you scan from phone, confirm connection works ...
# ... press y in terminal ...
# ... VM destroyed
```

Required for fully validating things the harness cannot automate: actual
client-app compatibility (v2rayNG, Streisand), real CDN behaviour, behaviour
under real network conditions.

## Orphan cleanup

If a run crashes or you `Ctrl+C` mid-provision, VMs may linger. The harness
tags every VM it creates with `meridian-realvm-test=1` plus a per-run
`meridian-fleet-id=<uuid>`. Find and destroy orphans:

```bash
# Show all harness-tagged VMs in your project
make real-lab-orphans

# Destroy them
make real-lab-down
```

`real-lab-down` destroys EVERY harness-tagged VM in the project — use with
care if you have multiple ongoing runs (unlikely in practice).

## What gets created (Hetzner)

Per run, for topology=single:

- 1 SSH key: `meridian-realvm-<fleet-id>` (public-key material from your
  `~/.ssh/id_ed25519.pub` or `MERIDIAN_TEST_SSH_KEY`)
- 1 server: `meridian-realvm-single-exit-1-<fleet-id>` (CX22, Ubuntu 24.04, Nuremberg)

All tagged with `meridian-realvm-test=1`, `meridian-fleet-id=<uuid>`,
`meridian-topology=single`.

Destroy path:
- VMs: deleted via API (instant)
- SSH key: best-effort removal (Hetzner reuses keys across projects — OK if
  left dangling, it's just a public key)

## Troubleshooting

**"HCLOUD_TOKEN is not set"** — generate a token at
https://console.hetzner.cloud → (your project) → Security → API Tokens. Give
it Read & Write permission. Export it in the shell session.

**"SSH on X.X.X.X:22 did not come up within 120s"** — VM booted but cloud-init
is still running. Rare, but can happen on first-ever image pull. Try again.

**"subscription URL returned HTTP 503"** — Remnawave panel didn't fully come
up. CX22 is the minimum viable size; if testing on smaller (not recommended),
bump to CX32.

**Stuck with orphan VMs after a crash** — `make real-lab-orphans` to list,
`make real-lab-down` to destroy.

## Why not Terraform / Pulumi?

Short answer: same Python code we use for this harness will eventually power
a user-facing `meridian deploy --create-vm hetzner` feature. An external IaC
tool would force end users to install Terraform or Pulumi just to deploy a
VPN — undesirable UX. Per-cloud SDK + abstract `CloudProvider` class gives
us:

- `pip install meridian-vpn[hetzner]` — one dependency
- No state file (label-based discovery — crashed run leaves tagged orphans
  that are easy to find)
- Full access to provider-specific features (Hetzner Primary IPs, /64 IPv6
  subnets)
- Under 1 second per API call vs ~5s through a Pulumi state round-trip

The `CloudProvider` abstract class lives at
`src/meridian/infra/providers/base.py`; Hetzner impl at
`src/meridian/infra/providers/hetzner.py`. Adding a new provider is one file
and one `pyproject.toml` optional dep.
