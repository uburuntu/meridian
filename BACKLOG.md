# Backlog

**Last updated:** 2026-03-21
**Version:** 3.1.0
**Source:** Five-reviewer grand assessment → executed in Waves 0–5 + E2E tested

---

## Strategic direction

**Ansible migration is underway.** The Python provisioner (`src/meridian/provision/`) is built, wired into `setup.py`, and E2E tested against a real server. Ansible playbooks are kept as `--legacy` fallback. Next step: delete `ansible.py` after one release cycle of production use.

**We are keeping 3x-ui.** It's powerful, actively maintained, and the web UI keeps power users on Meridian. The coupling is contained in `PanelClient`.

---

## What's done (v3.1.0)

<details>
<summary>Waves 0–5 completed in this release (click to expand)</summary>

### Wave 0 — Protocol Foundation
- [x] Move `Inbound` from `panel.py` to `models.py`
- [x] DRY `client_settings()` into base `Protocol` class
- [x] Create `ProtocolURL` dataclass for generic output
- [x] Change `PROTOCOLS` from list to `dict[str, Protocol]` with `PROTOCOL_ORDER`
- [x] Add `display_label` property, remove dead `url_scheme` field

### Wave 1 — Bugs + Error Handling
- [x] Fix XHTTP `client_total_bytes` division (was raw bytes, now GiB like Reality/WSS)
- [x] Validate `json.success` on default panel login
- [x] Add `| quote` filter to QR shell tasks (shell injection fix)
- [x] Move DNS check to `pre_tasks` (fails fast before Docker/Xray deploy)
- [x] Replace `assert` with explicit `ValueError` checks
- [x] Add `fail()` error taxonomy: `hint_type="user|system|bug"`
- [x] Fix silent `except Exception` blocks (now emit `warnings.warn`)
- [x] Fix type annotations (`conn: object` → `conn: ServerConnection`)
- [x] Make `PanelClient` a context manager
- [x] Extract `SSH_OPTS` constant

### Wave 2 — Output Restructure + Testing
- [x] Split `output.py` → `urls.py` + `render.py` + `display.py`
- [x] Generic `list[ProtocolURL]` iteration (no more `if urls.xhttp:`)
- [x] Graceful QR degradation (hide div when empty)
- [x] 18 new `test_client.py` tests (run_add, run_list, run_remove)
- [x] `test_render_templates.py` (pytest, auto-discovered)
- [x] `resolve_and_connect()` helper + tests

### Wave 3 — Provisioner Foundation
- [x] `Step`/`StepResult`/`ProvisionContext`/`Provisioner` abstractions
- [x] 6 common steps: packages, auto-upgrades, timezone, SSH hardening, BBR, firewall
- [x] 2 Docker steps: install Docker, deploy 3x-ui container
- [x] `ConfigurePanel`: generate keys, save creds, apply settings
- [x] `LoginToPanel`: reusable login step
- [x] 3 inbound creators: Reality, XHTTP, WSS (parameterized, idempotent)
- [x] `VerifyXray`: process health check
- [x] `InstallHAProxy`: config template + validation
- [x] `InstallCaddy`: DNS pre-check, config, connection page
- [x] 15 total provisioning steps

### Wave 4 — Migration Completion
- [x] `build_setup_steps(ctx)` orchestrator assembling full pipeline
- [x] `setup.py` rewired to use Python provisioner (default)
- [x] `--legacy` flag for Ansible fallback
- [x] `ProvisionContext` dict-like access for inter-step state
- [x] Unified `StepResult` imports (was duplicated 3x)
- [x] `conn.run(sudo=...)` parameter for non-root SSH users
- [x] `PanelClient` uses `sudo=False` for curl commands
- [x] Saved panel port respected on re-runs

### Wave 5 — UX + Docs
- [x] Jargon → plain language: "inbound" → "configuration", "SNI" → "camouflage target"
- [x] `--ai` flag promoted in diagnostics output
- [x] Wizard intro: human benefit first, technical details after
- [x] README: emotional hook, common scenarios, threat model link, supported platforms
- [x] AI docs drift fixed (stale "downloads playbooks", removed `*-clients.yml`)
- [x] Regenerated `ai-reference.md`

### E2E Testing
- [x] Tested against real Ubuntu 24.04 server (non-root + sudo)
- [x] All 15 provisioner steps pass
- [x] `client add/list/remove` verified
- [x] `ping` verified (clock, port, TLS handshake)
- [x] 3 bugs found and fixed during E2E

</details>

---

## Next up

### Ansible cleanup (post v3.1.0 stabilization)

After one release cycle confirms the Python provisioner is stable:

- [ ] **Delete `ansible.py`** — `ensure_ansible()`, `ensure_collections()`, `run_playbook()`, `write_inventory()`
- [ ] **Remove `--legacy` flag** from `setup.py` and `cli.py`
- [ ] **Move playbooks to `playbooks-legacy/`** or delete entirely
- [ ] **Update CI** — remove ansible-lint, ansible-check, dry-run jobs
- [ ] **Update Makefile** — remove ansible-specific targets
- [ ] **Drop Ansible from install.sh** — no more lazy Ansible bootstrap

### Provisioner hardening

- [ ] **Uninstall provisioner** — reverse of setup steps, replaces `playbook-uninstall.yml`
- [ ] **Domain mode E2E test** — test HAProxy + Caddy + WSS provisioner against a server with a domain
- [ ] **Fresh server E2E test** — test full provisioner on a clean VPS (no existing Docker/panel)
- [ ] **Provisioner unit tests** — mock `conn.run()` for each step, test idempotency checks
- [ ] **Domain prompt yes/no gate** — replace `Domain [skip]:` with "Do you have a domain? [y/N]"

### Scale features (Wave 6)

- [ ] **Batch client add** — `meridian client add alice bob charlie` (single SSH session)
- [ ] **Client migration for rebuilds** — detect clients on old server, re-create on new
- [ ] **Cross-server `meridian status`** — all servers + client counts in one view
- [ ] **Per-client traffic/IP limits** — `--limit-gb 100 --limit-ip 3`

---

## Icebox

- [ ] Subscription URL support for client management at scale
- [ ] Key/credential rotation without full uninstall/reinstall
- [ ] Proactive IP block notification (Telegram/webhook alerts)
- [ ] Zero-to-VPN onboarding wizard on meridian.msu.rocks
- [ ] Password-protected connection info page
- [ ] Shell completion support (typer built-in)
- [ ] Website section reorder (Setup → What Happens → Connect → Technology)
- [ ] Add deployed version to diagnostics (`/etc/meridian/version`)
- [ ] Add "broke after update" issue template

---

## Completed (historical)

<details>
<summary>Pre-v3.1.0 items</summary>

- [x] Replace `eval` with `printf -v` — code injection fix
- [x] Rewrite CLI in Python — 1,727-line bash → modular Python package
- [x] Gate CD/Release on CI success
- [x] Add `body_format` policy check in CI
- [x] Auto-discover templates in render test
- [x] Add connection-info app link sync check
- [x] Add Xray health check after inbound creation
- [x] Fix CLI server install for non-root users
- [x] Add `apt` fallback for Ansible installation
- [x] Retry Ansible collection install (3x)
- [x] Validate VERSION format in CI
- [x] Extract YAML → `ServerCredentials` dataclass
- [x] Standardize flag parsing via typer
- [x] Docker integration test for 3x-ui API
- [x] PyPI trusted publisher + registration
- [x] Consolidate connection-info HTML templates
- [x] Add mypy type checking to CI
- [x] SHA256 checksum verification for auto-update
- [x] Make shellcheck blocking in CI

</details>
