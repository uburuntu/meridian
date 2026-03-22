# Backlog

Prioritized task list for Meridian development.
Version history is in [CHANGELOG.md](CHANGELOG.md).

---

## Next up

### Provisioner hardening

- [ ] Domain mode E2E test (HAProxy + Caddy + WSS on a server with domain)
- [ ] Provisioner unit tests (mock `conn.run()`, test idempotency checks) — priority: `ConfigurePanel`, `CreateRealityInbound`, `LoginToPanel`
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
- [ ] Delete stale `output.py` legacy facade — `build_vless_urls()` and `ClientURLs` unused, migrate `test_output.py`

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

- [ ] `meridian client show NAME` — regenerate connection info without destroying and recreating the client
- [ ] `client list` usage stats — surface last connected time and traffic from 3x-ui API
- [ ] IPv6 support — currently IPv4-only (`is_ipv4` validation, `curl -4` for IP detection)
- [ ] Subscription URL support — expose 3x-ui's `subEnable` for auto-config updates on IP change

### Scale features

- [ ] Batch client add (`meridian client add alice bob charlie`)
- [ ] Client migration for rebuilds (detect clients on old server, re-create)
- [ ] Cross-server `meridian status`
- [ ] Per-client traffic/IP limits (`--limit-gb`, `--limit-ip`)

---

## Icebox

- [ ] Key/credential rotation without reinstall
- [ ] Proactive IP block notification (Telegram/webhook)
- [ ] Zero-to-VPN onboarding wizard on website
- [ ] Password-protected connection info page
- [ ] Shell completion (typer built-in)
- [ ] Deployed version in diagnostics
- [ ] "Broke after update" issue template
- [ ] Remove v1→v2 credential migration (sunset old format)
- [ ] `conn.run()` complexity — four-variable truth table for execution modes (split into `RemoteConnection`/`LocalConnection`)
- [ ] `_render_stats_script()` embeds 127-line Python program as f-string — move to template file
- [ ] `check.py:run()` is 234-line monolith — extract checks into individual functions
- [ ] `client.py:run_add()` is 146 lines doing 8+ things — extract helper functions
