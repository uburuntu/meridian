# Backlog

**Last updated:** 2026-03-21
**Version:** 3.3.0

---

## Strategic direction

**Ansible is fully purged.** All code, docs, templates, comments, and CI references to Ansible have been removed. The Python provisioner is the only deployment engine. CLAUDE.md rewritten to reflect the provisioner architecture.

**We are keeping 3x-ui.** Coupling is contained in `PanelClient` (API methods now public).

---

## What shipped in v3.3.0

- **Bug fix:** `--xhttp` flag was always True (`xhttp or True`), now `--xhttp/--no-xhttp` toggle defaulting on
- **Bug fix:** `InstallHAProxy` status always "changed" (copy-paste), `ConfigureFirewall` idempotency was fake
- **Ansible purge (88 files, -3,785 lines net):** removed from CLAUDE.md (~40% rewritten), website, AI docs, GitHub templates, CONTRIBUTING, SECURITY, code comments, variable names (`ansible_user`→`ssh_user`), diagnostics (removed Ansible version check), `ai.py` prompt, `protocols.py` comments, `ssh.py` docstrings, template variable (`ansible_date_time`→`generated_at`)
- **Provisioner refactor:** `_timed` decorator deduplicated (3→1), `PanelClient` private methods promoted to public API, client settings builders consolidated (3→1), `ctx` type annotations fixed (`dict[str,Any]`→`ProvisionContext`)
- **UX improvements:** setup success celebration message, better error messages, `--ai` help text updated, scanner "Skipped" → friendly message, `Install`→`Setup` tab on website, i18n for SNI/XHTTP hints
- **Output cleanup:** ALL CAPS client header → title case with checkmark, Ansible template refs → Jinja2, broad `except Exception` narrowed
- **Dead code removed:** `resolve_and_connect()`, `inventory.yml.example`, unused imports
- **Architecture docs rewritten:** `docs/architecture.md` now describes Python provisioner steps
- **E2E verified:** setup, --no-xhttp, idempotent re-run, client add/list/remove, uninstall, ping, check, diagnostics — all on real Ubuntu 24.04 server with non-root sudo user

## What shipped in v3.1.0–3.2.0

- Python provisioner engine (15 steps replacing all Ansible roles)
- Ansible fully deleted (-2,825 lines): playbooks, roles, ansible.py, CI jobs
- Uninstall provisioner (replaces playbook-uninstall.yml)
- Protocol foundation (ProtocolURL, dict registry, DRY base class)
- Output split into urls.py / render.py / display.py
- Error taxonomy, sudo escalation, PanelClient context manager
- E2E tested: 2 full setup→client→uninstall→setup cycles on real server
- README emotional hook, common scenarios, AI docs fixes

---

## Next up

### Provisioner hardening

- [ ] Domain mode E2E test (HAProxy + Caddy + WSS on a server with domain)
- [ ] Provisioner unit tests (mock `conn.run()`, test idempotency checks)
- [ ] Domain prompt yes/no gate (replace `Domain [skip]:`)

### Architecture debt (from code review)

- [ ] Complete output.py migration — move `client.py` imports to `urls.py`/`render.py`/`display.py`, delete legacy facade
- [ ] Make protocol abstraction truly generic (currently 5+ files hardcode reality/xhttp/wss keys)
- [ ] Add typed fields to `ProvisionContext` for inter-step state (credentials, panel, xray_cmd)
- [ ] Partial client add rollback (if Reality succeeds but WSS fails, clean up)
- [ ] `ServerConnection.check_ssh()` raises `typer.Exit` — should raise domain exception

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
- [ ] Ping web tool i18n (4 languages like main site)
- [ ] macOS app recommendation in HTML connection page
- [ ] Progress feedback during provisioning (per-step status lines)
- [ ] Remove v1→v2 credential migration (sunset old format)
