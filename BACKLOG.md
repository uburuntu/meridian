# Backlog

**Last updated:** 2026-03-20
**Version:** 2.0.0

---

## P0 — Critical (done)

- [x] Replace `eval` with `printf -v` in `prompt()` to prevent code injection
- [x] Add SHA256 checksum verification to auto-update
- [x] Make shellcheck blocking in CI (was `|| true`, no-op)
- [x] Fix auto-update downgrade when running dev version (semver direction check)
- [x] Fix `eval` injection vector in `prompt()` function
- [x] **Rewrite CLI in Python** — migrated 1,727-line bash script to modular Python package (typer + rich + PyYAML)

## P1 — High (done)

- [x] Gate CD and Release workflows on CI success (`workflow_run` chain)
- [x] Add `body_format` policy check in CI (prevent form-urlencoded on inbound/client APIs)
- [x] Auto-discover templates in render test (was manual list, missed `update-stats.py.j2`)
- [x] Add connection-info app link sync check in CI
- [x] Add Xray health check after inbound creation (catch crash loops)
- [x] Fix CLI server install for non-root users (sudo mv fallback)
- [x] Suggest `meridian uninstall` + retry on inbound creation failures
- [x] Add `apt` fallback for Ansible installation (WSL compat)
- [x] Retry Ansible collection install up to 3 times (flaky networks)
- [x] Validate VERSION format in CI — `^\d+\.\d+\.\d+$`
- [x] Extract YAML parsing into structured credentials — `ServerCredentials` dataclass replaces 10+ `grep|awk|tr` instances
- [x] Standardize flag parsing — typer decorators replace 8 duplicate `while/case` blocks

## P1 — High (open)

- [ ] Pin ansible-lint via `gh_action_ref: "v25.5.0"` — `@main` is upstream-recommended but a breaking change could randomly fail CI
- [ ] Add `ansible.cfg` validation to CI — verify `jinja2_native = True` exists (critical for `body_format: json` integer typing)
- [x] Add Docker integration test for 3x-ui API — spin up 3x-ui in CI, run login/create-inbound/list/verify JSON round-trip
- [x] Configure PyPI trusted publisher — required for automated PyPI publishing from GitHub Actions
- [x] Register `meridian-vpn` on PyPI — publish initial package to reserve name

## P2 — Medium (open)

- [ ] Add deployed playbook version to diagnostics — write VERSION to `/etc/meridian/version` during deploy, read in `meridian diagnostics` to catch version mismatch
- [ ] Consolidate 2 connection-info HTML templates into one — use `{% if domain_mode %}` conditionals instead of 2 copies
- [ ] Add "broke after update" issue template — capture old version, new version, timing, auto-update vs manual
- [ ] Improve dry-run CI job — remove `|| echo` suppression, use `--tags` for local-compatible tasks, add domain mode dry-run
- [x] ~~Add playbook sync automation~~ — eliminated by single-copy architecture (playbooks only in `src/meridian/playbooks/`)
- [ ] Add mypy type checking to CI — strict mode on `src/meridian/`

## P3 — Low (open)

- [ ] Add VERSION semver validation in release workflow (not just CI)
- [ ] Replace `MockUndefined` in template tests with stricter undefined handling
- [ ] Add HTML validation for rendered connection-info templates
- [ ] Add docs/ drift detection in CI — verify `docs/` copies match source files
- [ ] Add lightweight opt-in telemetry — anonymous ping on setup success (version, OS, mode)

## Future — Architecture (open)

- [ ] Proactive IP block notification — scheduled reachability check with Telegram/webhook alerts
- [ ] Self-steal mode — Reality masquerades as your own domain
- [ ] Zero-to-VPN onboarding wizard on meridian.msu.rocks
- [ ] Password-protected connection info page for family sharing
- [ ] Key/credential rotation without full uninstall/reinstall
- [ ] Shell completion support — typer has built-in completion generation
