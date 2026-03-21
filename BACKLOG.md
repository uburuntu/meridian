# Backlog

**Last updated:** 2026-03-21
**Version:** 3.3.1

---

## Strategic direction

**Ansible is fully purged.** All code, docs, templates, comments, and CI references to Ansible have been removed. The Python provisioner is the only deployment engine. CLAUDE.md rewritten to reflect the provisioner architecture.

**We are keeping 3x-ui.** Coupling is contained in `PanelClient` (API methods now public).

---

## What shipped in v3.3.1

- **Bug fix:** Uninstall cron grep pattern (`meridian-`) never matched actual cron entry (`update-stats.py`) — stats cron job was never cleaned up
- **Bug fix:** i18n `textContent` stripped the ping test `<a>` link for RU/FA/ZH users — restructured to separate `data-t` elements
- **Bug fix:** `test_panel.py` body format test used `assert X or Y` which always passed — now properly verifies JSON-string-inside-JSON encoding
- **Code quality:** Completed output.py migration — `client.py` now imports from `urls.py`/`render.py`/`display.py` directly, `output.py` reduced from 449→140 lines (thin backwards-compat wrappers)
- **Code quality:** Centralized magic values (`DEFAULT_SNI`, `DEFAULT_FINGERPRINT`, `DEFAULT_PANEL_PORT`) in `config.py`, replacing ~25 scattered literals across 12 files
- **Code quality:** Fixed `resolved: object` typing in `setup.py` — proper `ResolvedServer` import, removed 6 `type: ignore` comments
- **Code quality:** Normalized provisioner step names to human-readable format (e.g. `"configure_panel"` → `"Configure panel"`)
- **Code quality:** Extracted `derive_client_name()` helper, removed `_PROTOCOL_LABELS` duplication, fixed dead conditional in `Provisioner.run()`
- **BACKLOG:** Added 17 strategic items with design options from 5-reviewer grand code review

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
- [ ] Provisioner unit tests (mock `conn.run()`, test idempotency checks) — priority: `ConfigurePanel`, `CreateRealityInbound`, `LoginToPanel`
- [ ] Domain prompt yes/no gate (replace `Domain [skip]:`)
- [ ] Credential file corruption test (`ServerCredentials.load()` with truncated/malformed YAML)

### Architecture debt

- [ ] Type `ProvisionContext` inter-step state — promote `ctx["credentials"]`, `ctx["panel"]`, `ctx["xray_bin"]` to typed Optional fields
  - **Option A:** Typed Optional fields on the dataclass (simple, IDE autocomplete, mypy coverage)
  - **Option B:** TypedDict for well-known keys (preserves dict access pattern)
  - **Option C:** Named constants for keys (minimal, just prevents typos)
- [ ] Make protocol abstraction honest — current ABC is VLESS-shaped, not truly protocol-agnostic
  - **Option A:** Rename to "VLESS transport registry" — honest about what it is, design true abstraction when needed
  - **Option B:** Generalize now — `build_url()` returns `ConnectionInfo` object, `client_settings()` becomes optional, backend-agnostic identity
  - **Recommendation:** Option A — premature abstraction worse than honest specialization
- [ ] Extract `PanelTransport` protocol — separate SSH+curl transport from 3x-ui API semantics
  - **Option A:** `PanelTransport` protocol with `request(method, path, body) -> dict` — SSH impl wraps curl, local impl uses `requests`
  - **Option B:** Keep current approach but add local-mode shortcut (skip SSH when `local_mode=True`)
- [ ] `console.fail()` → domain exceptions — decouple from Typer
  - **Option A:** `MeridianError` hierarchy, catch at CLI boundary (`main_callback`)
  - **Option B:** Keep `fail()` as-is for commands, add `SSHError`/`PanelError` for library code only
- [ ] Partial client add rollback (if Reality succeeds but WSS fails, clean up added entries)

### Security hardening

- [ ] SSH host key verification — `StrictHostKeyChecking=accept-new` enables TOFU MitM (critical in censored-region threat model)
  - **Option A:** Switch to `yes` with `--accept-new-host-key` flag for first connection
  - **Option B:** Prompt user with host key fingerprint before accepting (like normal SSH)
  - **Option C:** Keep `accept-new` but document the risk prominently
- [ ] Docker image digest pinning — 3x-ui pinned by tag, not sha256 digest
  - **Option A:** Pin to `@sha256:...`, update digest manually when upgrading
  - **Option B:** Fetch and verify digest at deploy time
- [ ] RealiTLScanner checksum verification — binary downloaded from GitHub and run as root without integrity check
  - Pin to specific version with hardcoded SHA256 hash
- [ ] XHTTP port deterministic from server IP — `hash(ip) % 10000` aids censor fingerprinting
  - **Option A:** Use `hashlib.sha256` instead of `hash()` (still deterministic but less predictable)
  - **Option B:** Random port stored in credentials (fully unpredictable, idempotent on re-run)
- [ ] `confirm()` defaults to yes without TTY — destructive ops auto-confirm in piped/CI contexts
  - Default to "no" for destructive operations (`uninstall`)
- [ ] Diagnostics secret redaction gaps — may miss base64 keys, web_base_path, info_page_path

### UX improvements

- [ ] File delivery gap — standalone mode (no domain) has no hosted connection page, only a local HTML file
  - **Option A:** `meridian client share NAME` — temporary local HTTP server with QR code to URL
  - **Option B:** Generate QR PNG image alongside HTML (can be texted as a photo)
  - **Option C:** Lightweight file-sharing via `transfer.sh` or similar ephemeral service
  - This is the biggest gap between vision ("grandma scans QR") and reality ("figure out how to deliver an HTML file")
- [ ] `meridian client show NAME` — regenerate connection info without destroying and recreating the client
- [ ] `client list` usage stats — surface last connected time and traffic from 3x-ui API
- [ ] IPv6 support — currently IPv4-only (`is_ipv4` validation, `curl -4` for IP detection)
- [ ] `qrencode` dependency check at install time — silently fails if not installed

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
- [ ] `conn.run()` complexity — four-variable truth table for execution modes (split into `RemoteConnection`/`LocalConnection`)
- [ ] `_render_stats_script()` embeds 127-line Python program as f-string — move to template file
- [ ] `check.py:run()` is 234-line monolith — extract checks into individual functions
- [ ] `client.py:run_add()` is 146 lines doing 8+ things — extract helper functions
