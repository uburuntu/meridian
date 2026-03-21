# Backlog

**Last updated:** 2026-03-21
**Version:** 3.1.0

---

## Strategic direction

**Ansible migration is underway.** The Python provisioner (`src/meridian/provision/`) is built, wired into `setup.py`, and E2E tested against a real server. Ansible playbooks are kept as `--legacy` fallback. Next step: delete `ansible.py` after one release cycle of production use.

**We are keeping 3x-ui.** It's powerful, actively maintained, and the web UI keeps power users on Meridian. The coupling is contained in `PanelClient`.

---

## What shipped in v3.1.0

- Python provisioner engine (15 idempotent steps replacing all 7 Ansible roles)
- Protocol foundation (`ProtocolURL`, dict registry, DRY base class)
- Output restructured into `urls.py` / `render.py` / `display.py`
- Error taxonomy (`fail(hint_type="user|system|bug")`)
- `conn.run(sudo=...)` for non-root SSH users
- 31 new tests (284 total), E2E tested on real server
- README emotional hook, common scenarios, AI docs drift fixes
- 4 Ansible bug fixes (XHTTP bytes, login validation, QR injection, DNS pre-flight)

---

## Next up

### Ansible cleanup (post v3.1.0 stabilization)

- [ ] Delete `ansible.py`, remove `--legacy` flag
- [ ] Move or delete playbooks
- [ ] Update CI — remove ansible-lint, ansible-check, dry-run jobs
- [ ] Drop Ansible from install.sh

### Provisioner hardening

- [ ] Uninstall provisioner (replaces `playbook-uninstall.yml`)
- [ ] Domain mode E2E test (HAProxy + Caddy + WSS)
- [ ] Fresh server E2E test (no existing Docker/panel)
- [ ] Provisioner unit tests (mock `conn.run()`, test idempotency)
- [ ] Domain prompt yes/no gate (replace `Domain [skip]:`)

### Scale features

- [ ] Batch client add (`meridian client add alice bob charlie`)
- [ ] Client migration for rebuilds (detect clients on old server, re-create)
- [ ] Cross-server `meridian status`
- [ ] Per-client traffic/IP limits (`--limit-gb`, `--limit-ip`)

---

## Icebox

- [ ] Subscription URL support
- [ ] Key/credential rotation without reinstall
- [ ] Proactive IP block notification (Telegram/webhook)
- [ ] Zero-to-VPN onboarding wizard on website
- [ ] Password-protected connection info page
- [ ] Shell completion (typer built-in)
- [ ] Website section reorder
- [ ] Deployed version in diagnostics
- [ ] "Broke after update" issue template
