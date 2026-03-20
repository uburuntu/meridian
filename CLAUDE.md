# CLAUDE.md

## Project overview

Ansible automation for deploying censorship-resistant VLESS+Reality proxy servers. Supports standalone single-server mode and a two-server relay chain for IP whitelist bypass.

## Architecture

- **Standalone mode** (`playbook.yml`): Single server with VLESS+Reality. Optional domain mode adds HAProxy (SNI routing), Caddy (TLS), and VLESS+WSS (CDN fallback via Cloudflare).
- **Chain mode** (`playbook-chain.yml`): Exit node (Germany) + Relay node (Russia on whitelisted IP). User connects to relay via plain VLESS+TCP; relay forwards to exit via VLESS+Reality+XHTTP.

### Key design decisions

- HAProxy on port 443 does TCP-level SNI routing without TLS termination, so both Reality and Caddy can coexist on port 443.
- 3x-ui panel is managed entirely via its REST API (no manual web UI steps).
- Caddy handles TLS automatically — email is optional, not required.
- Caddy config uses import pattern: Meridian writes to `/etc/caddy/conf.d/meridian.caddy`, main Caddyfile just has `import /etc/caddy/conf.d/*.caddy`. User's own Caddyfile is never overwritten.
- Credentials are persisted locally in `~/meridian/<host>.yml` for idempotent re-runs. Credentials are saved BEFORE changing the panel password to prevent lockout on failure.
- Uninstall deletes credentials from both server and local machine to prevent stale state on reinstall.
- Docker installation is skipped if Docker is already running with containers.
- In no-domain mode, the panel binds to localhost only (SSH tunnel required).
- 3x-ui Docker image is pinned to a tested version (`threexui_version` in group_vars) to prevent API breakage.
- All tasks handling secrets use `no_log: true` to keep credentials out of terminal output.

## Project structure

```
pyproject.toml             Python package config (hatchling build, PyPI as meridian-vpn)
VERSION                    Version source of truth (read by hatchling + importlib.metadata)
src/meridian/              Python CLI package
  __init__.py              Version from importlib.metadata
  __main__.py              python -m meridian support
  cli.py                   Typer app, subcommand registration, global --server flag
  config.py                Paths, URLs, constants
  console.py               Rich terminal output: info/ok/warn/fail/prompt/confirm
  credentials.py           ServerCredentials dataclass, YAML load/save
  servers.py               ServerRegistry: list/find/add/remove
  ssh.py                   ServerConnection: run, check_ssh, detect_local_mode
  ansible.py               Playbook execution, Ansible bootstrap, inventory generation
  update.py                Auto-update via PyPI (semver: auto-patch, prompt minor/major)
  ai.py                    AI prompt building, clipboard, doc fetching
  commands/                One module per subcommand
    resolve.py             Server resolution logic (shared by most commands)
    setup.py               Interactive wizard + playbook execution
    client.py              client add/list/remove (list=direct API, add/remove=ansible)
    server.py              server add/list/remove
    check.py               Pre-flight validation (SNI, ports, DNS, OS, disk, clock)
    scan.py                RealiTLScanner download + execution + SNI selection
    ping.py                Reachability test (TCP, TLS, clock drift)
    diagnostics.py         System info collection + redaction
    uninstall.py           Playbook execution + credential cleanup
  playbooks/               Bundled Ansible playbooks (package_data)
    playbook.yml           Standalone mode
    playbook-chain.yml     Chain mode
    playbook-client.yml    Client management
    playbook-uninstall.yml Clean removal
    ansible.cfg            Ansible configuration
    requirements.yml       Galaxy collections
    group_vars/            Shared defaults
    roles/                 All Ansible roles
playbook.yml               Standalone mode (repo root copy, used by CI)
playbook-chain.yml         Chain mode
playbook-client.yml        Client management
playbook-uninstall.yml     Clean removal
group_vars/                Shared defaults (repo root copy)
roles/                     All Ansible roles (repo root copy)
install.sh                 CLI installer (bootstraps uv, installs from PyPI, migrates old bash CLI)
setup.sh                   Compat shim → installs CLI + forwards args
tests/
  test_cli.py              CliRunner smoke tests
  test_credentials.py      Credential dataclass tests
  test_servers.py          Server registry tests
  test_ansible.py          Inventory generation + playbook bundling tests
  test_update.py           Version comparison + update throttle tests
  render_templates.py      Jinja2 template rendering test (with Ansible filter mocks)
  conftest.py              Shared fixtures
docs/index.html            Website hosted on meridian.msu.rocks (GitHub Pages)
docs/install.sh            Installer served from website (CD sync)
docs/setup.sh              Compat shim served from website (CD sync)
docs/version               Version file served from website (CD sync)
docs/ping.html             Web-based ping tool (server reachability test)
docs/CNAME                 Custom domain for GitHub Pages
.github/workflows/ci.yml   CI: ansible-lint, pytest, ruff, shellcheck, dry-run
.github/workflows/cd.yml   CD: sync install.sh/setup.sh/version → docs/
.github/workflows/release.yml  Release: git tag + GitHub Release + PyPI publish
.ansible-lint              Ansible lint configuration
SECURITY.md                Vulnerability reporting policy
CONTRIBUTING.md            Development setup and PR guidelines
```

## Implicit dependencies & cross-file relationships

These are easy to break by editing one file without updating the others:

### CLI architecture
- `meridian` CLI is a Python package (`meridian-vpn` on PyPI), installed via `uv tool install` or `pipx install`
- Built with typer (CLI framework) + rich (terminal output) + PyYAML (credential management)
- Data directory: `~/.meridian/` (credentials, cache, servers, inventory)
- Playbooks bundled inside the Python package (`src/meridian/playbooks/`), accessed via `importlib.resources`
- Credentials cached locally in `~/.meridian/credentials/<IP>/` (per-server subdirectories)
- Server as source of truth: credentials stored at `/etc/meridian/` on the server (synced by playbook post_tasks)
- Server index: `~/.meridian/servers` (line-oriented: `host user name`, no spaces in names)
- Auto-update checks PyPI JSON API (throttled to 1x/60s); auto-patches via `uv tool upgrade` / `pipx upgrade`
- `VERSION` file at repo root is the single source of truth — read by hatchling at build time, by `importlib.metadata` at runtime
- `setup.sh` is a compat shim that installs the CLI and forwards args
- Ansible is NOT a Python dependency — installed lazily via `ensure_ansible()` (pipx → pip3 → apt cascade)

### meridian CLI ↔ playbooks
- CLI passes `-e server_public_ip=... -e credentials_dir=...` to ansible-playbook via `ansible.run_playbook()`
- All output templates use `{{ server_public_ip }}` instead of `{{ ansible_host }}` for user-facing URLs
- CLI writes `inventory.yml` to `~/.meridian/inventory.yml` (not inside package dir — may be read-only)
- CLI sets `ANSIBLE_CONFIG` env var pointing to bundled `ansible.cfg`, runs with `cwd=playbooks_dir`
- CLI adds `ansible_connection: local` when running on the target server itself
- CLI adds `ansible_become: true` for non-root users
- Playbook post_tasks sync `credentials_dir` to `/etc/meridian/` on the server (unless already local)
- Playbooks exist in two places: repo root (for CI/development) and `src/meridian/playbooks/` (bundled in package)

### meridian subcommands
- `meridian setup [IP] [--domain --sni --xhttp --name --user --yes]` — deploy server
- `meridian client add|list|remove NAME` — manage clients via `playbook-client.yml`
- `meridian server add|list|remove` — manage known servers
- `meridian check [IP] [--ai]` — pre-flight validation (SNI, ports, DNS, OS, disk, ASN)
- `meridian scan [IP]` — find optimal SNI targets via RealiTLScanner on server
- `meridian ping [IP]` — test proxy reachability from client device (no SSH needed)
- `meridian diagnostics [IP] [--ai]` — collect system info for bug reports
- `meridian uninstall [IP]` — remove proxy via `playbook-uninstall.yml`
- `meridian self-update` — update CLI via `uv tool upgrade` / `pipx upgrade`
- `meridian version` — show version

### docs/index.html ↔ meridian CLI
- Website command builder has tabbed interface generating `meridian` subcommands
- Install files served from `meridian.msu.rocks/` — synced by CD workflow: `install.sh`, `setup.sh`, `version`
- CLI itself distributed via PyPI (`meridian-vpn`), not served from website
- Website references the same app download links as the HTML templates in roles
- `docs/ping.html` — standalone web ping tool, uses `fetch()` timing to test server reachability from browser. Supports URL params (`?ip=...&domain=...&name=...`) for shareable pre-filled links. Stores server history in localStorage.

### Connection info HTML templates (3 copies)
- `roles/caddy/templates/connection-info.html.j2` — served on the server (domain mode)
- `roles/output/templates/connection-info.html.j2` — saved locally (standalone/exit)
- `roles/output_relay/templates/connection-info.html.j2` — saved locally (relay)
- All three have similar CSS/JS but different Jinja2 variables; app download links must be kept in sync across all three

### Credential flow
- Server is source of truth: `/etc/meridian/proxy.yml` on the server
- Local cache: `~/.meridian/credentials/<IP>/proxy.yml` per server
- `meridian` CLI passes `credentials_dir=$HOME/.meridian/credentials/$SERVER_IP` (remote) or `/etc/meridian` (local mode)
- `roles/xray/tasks/configure_panel.yml` saves to `{{ credentials_file }}` which is `{{ credentials_dir }}/{{ inventory_hostname }}.yml`
- `roles/xray/tasks/configure_panel.yml` also creates `{{ credentials_dir }}/{{ inventory_hostname }}-clients.yml` with the first client
- `playbook.yml` and `playbook-client.yml` post_tasks sync `credentials_dir` to `/etc/meridian/` on the server
- `playbook-chain.yml` relay play loads EXIT node credentials from `{{ credentials_dir }}/{{ exit_node }}.yml`
- Domain is saved to credentials file for detection on re-runs
- CLI reads saved credentials to find the server IP (for client/uninstall/diagnostics commands)
- CLI fetches credentials from `/etc/meridian/` via SSH when not found locally (handles cross-machine runs)
- `meridian server add IP` fetches credentials from server, caches locally

### Client management flow
- `playbook-client.yml` loads credentials from `proxy.yml`, reads `domain` field to detect domain mode
- Client names map to 3x-ui `email` fields: `reality-{name}`, `wss-{name}`, `xhttp-{name}` (e.g., `reality-alice`, `wss-alice`, `xhttp-alice`)
- The first client created during install uses `reality-{{ first_client_name | default('default') }}` — same naming convention
- Clients are tracked in `{{ credentials_dir }}/{{ inventory_hostname }}-clients.yml` with UUIDs and timestamps
- `roles/output/tasks/generate_client_output.yml` is shared between the `output` role and `client_management` role
- 3x-ui API: `addClient` adds to existing inbound (id in form body), `delClient/{uuid}` removes by client UUID (NOT email — email silently succeeds but doesn't delete)
- `--add-client`/`--remove-client` resolve server IP from saved credentials (same as `--uninstall`)

### Caddy config pattern
- Meridian writes to `/etc/caddy/conf.d/meridian.caddy` (not the main Caddyfile)
- Main Caddyfile gets a single `import /etc/caddy/conf.d/*.caddy` line added via `lineinfile`
- Uninstall removes only `/etc/caddy/conf.d/meridian.caddy`, not the user's Caddyfile
- `meridian setup` interactive wizard checks saved credentials for domain suggestion

### Port 443 pre-check allowlist
- `roles/xray/tasks/deploy.yml` checks port 443 and allows `3x-ui`, `xray`, `haproxy`, `caddy` — if a new service is added to the stack, add it here too

### Panel health check URL
- After first run, the panel root `/` returns 404 (webBasePath is set) — health check accepts 404 as "responsive"
- Post-restart health checks in `configure_panel.yml` use `/{{ panel_web_base_path }}/` (guaranteed set at that point)
- The panel needs a `docker restart` after changing `webBasePath` (setting doesn't apply live)

### Xray binary path
- Binary is at `/app/bin/xray-linux-*` inside the 3x-ui container (architecture-dependent)
- Discovered dynamically via `ls` glob — stored in `xray_cmd` fact
- Used in both `roles/xray/tasks/configure_panel.yml` and `roles/xray_relay/tasks/configure_panel.yml`
- x25519 output format: `PrivateKey:` and `Password:` (not `Private key:` / `Public key:` in newer Xray versions)
- Parsing uses regex with both old and new format patterns; assertion verifies keys were parsed

### Handler flush timing
- `roles/output/tasks/main.yml` calls `meta: flush_handlers` before the port verification check
- Without this, HAProxy/Caddy handlers haven't fired yet and port 443 shows as not listening

### Terminal output rendering
- QR codes and connection summary use `ansible.builtin.shell` with `printf`/`cat` instead of `debug msg:` — this is required because Ansible's debug module JSON-escapes ANSI codes, making QR codes unreadable
- The `ansible.cfg` must NOT have `result_format = yaml` for the same reason

### Feedback loop
- `fail()` in meridian CLI suggests `meridian diagnostics` and links to GitHub issues
- Success output mentions feedback URL
- Ansible connection summary includes feedback section
- Website has troubleshooting with `meridian check` and `meridian diagnostics` commands
- README has troubleshooting section

## Key API patterns

- 3x-ui login: `POST /login` (form-urlencoded) returns session cookie. Login MUST use form-urlencoded (not JSON).
- Add inbound: `POST /panel/api/inbounds/add` (JSON body with `body_format: json`). The `settings`, `streamSettings`, `sniffing` fields must be JSON **strings** (not nested objects). The Go struct uses `string` type for these fields. With `body_format: json` + `jinja2_native = True`, the `>-` YAML blocks containing mixed text+Jinja2 expressions remain strings (Jinja2 NativeEnvironment only returns native types for single-expression templates like `{{ x }}`, not mixed content).
- List inbounds: `GET /panel/api/inbounds/list` (check by remark before creating)
- **CRITICAL: Do NOT use `body_format: form-urlencoded` for inbound/client API calls.** Ansible's uri module silently corrupts inline JSON values in form-urlencoded bodies — the API returns `success: true` but stores only the first key name instead of the full JSON object. This was a production bug. Always use `body_format: json` for inbound operations.
- 3x-ui rejects duplicate ports — two inbounds cannot share the same port. XHTTP needs its own dedicated port separate from Reality TCP.
- Update settings: `POST /panel/setting/update` (JSON body)
- Update credentials: `POST /panel/setting/updateUser` (JSON body)
- Read settings: `POST /panel/setting/all`
- Xray template config: set `xrayTemplateConfig` field in `/panel/setting/update`
- Key generation: `docker exec 3x-ui sh -c '/app/bin/xray-linux-* x25519'` (parse PrivateKey/Password lines), `docker exec 3x-ui sh -c '/app/bin/xray-linux-* uuid'`

## Build and test

```bash
# Install CLI in editable mode with dev dependencies
pip install -e ".[dev]"

# Run Python tests
pytest tests/ -v

# Run linter
ruff check src/ tests/
ruff format --check src/ tests/

# Run template rendering test
python3 tests/render_templates.py

# Install Ansible for playbook validation
pip install ansible
ansible-galaxy collection install -r requirements.yml

# Run standalone
ansible-playbook playbook.yml

# Run chain mode
cp inventory-chain.yml.example inventory-chain.yml
ansible-playbook -i inventory-chain.yml playbook-chain.yml

# The playbook verifies ports are listening at the end.
# To fully test, import the VLESS URL into v2rayNG and check connectivity.
```


## Conventions

- All tasks use FQCNs (e.g., `ansible.builtin.uri`, not `uri`)
- API responses are validated with `ansible.builtin.assert` checking `.json.success`
- Tasks handling secrets use `no_log: true`
- Conditional roles use `include_tasks` (not `import_tasks`) with `when`
- Port variables use deterministic random seeds (`inventory_hostname + suffix`) for idempotency
- QR codes generated with `qrencode` — must be installed on the local machine
- Cross-platform: `base64 | tr -d '\n'` instead of `base64 -w0` (macOS compat on localhost tasks; remote tasks can use `-w0` since remote is always Linux)
- XHTTP transport doesn't support `xtls-rprx-vision` flow (must be empty string)
- Docker compose errors include `rescue` blocks with container logs and common fix suggestions
- DNS resolution check for domain mode fails hard (override with `-e skip_dns_check=true`)
- Use `ansible_facts['distribution']` not `ansible_distribution` (deprecated in 2.24)
- Docker role removes conflicting `docker.io` / `containerd` / `runc` packages only when `docker-ce` is not already installed AND no containers are running
- `reality_dest` is derived from `reality_sni` (`{{ reality_sni }}:443`) — don't hardcode separately
- **SNI target selection**: Never recommend apple.com or icloud.com (Apple-owned ASN — mismatch with VPS hosting is instantly detectable). Good choices: www.microsoft.com, www.twitch.tv, dl.google.com, github.com (global CDN, shared infrastructure). Best: run `meridian scan` for same-network targets.
- **Always use context7 MCP to check up-to-date docs** before writing or modifying code that depends on external tools/libraries (Ansible, Docker, Caddy, GitHub Actions, shellcheck, etc.) — stale patterns and outdated common knowledge cause real deployment failures. Don't rely on training data for API syntax, CLI flags, or workflow configuration — verify against current docs first.
- **curl|bash stdin trap**: in `install.sh` and `setup.sh` (compat shim), any command that reads stdin MUST have `</dev/null` — the `meridian` CLI runs directly so this isn't needed there, but `</dev/null` on SSH commands is still good practice
- **Ansible debug vs shell for terminal output**: use `shell` with `printf`/`cat` for output containing ANSI codes (QR codes); `debug msg:` JSON-escapes them
- **pip3 install on modern Debian/Ubuntu**: must handle PEP 668 "externally managed environment" — try pipx, then `--user`, then `--break-system-packages`, then apt
- **pip user bin PATH**: after pip3 install --user, add `~/.local/bin` (Linux) and `~/Library/Python/*/bin` (macOS) to PATH
- **meridian interactive prompts**: `console.prompt()` reads from `/dev/tty` for pipe safety; detect public IPv4 with `curl -4` to avoid IPv6; suggest domain from saved credentials
- **console output functions**: `info()`, `ok()`, `warn()`, `fail()` use Rich markup — pass plain text, not ANSI codes. `fail()` raises `typer.Exit(1)` and is testable with CliRunner.
- **GitHub raw CDN caching**: raw.githubusercontent.com caches for ~60-120s; can't bust with query params or headers, just wait. Serving from meridian.msu.rocks avoids this.
- **HAProxy health checks**: do NOT use `check` on TLS backends (Caddy, Xray) — TCP probes fail on TLS-only ports, causing "backend has no server available" errors. These are local systemd services, not load-balanced pools.
- **docs/ sync**: `docs/install.sh`, `docs/setup.sh`, `docs/version` are synced by CD workflow. Manual edits to docs/ copies will be overwritten. CLI is no longer synced to docs/ (distributed via PyPI).
- **AI docs**: Source files in `docs/ai/` (`context.md`, `architecture.md`, `troubleshooting.md`). CD workflow concatenates them into `docs/ai/reference.md` — the single file the CLI fetches. Edit the source files, not `reference.md`.
- **`--ai` flag**: `meridian check --ai` and `meridian diagnostics --ai` bundle AI docs + command output into a clipboard-ready prompt for ChatGPT/Claude. Docs are cached at `~/.meridian/cache/ai-reference.md`, invalidated on version change.
- **VERSION consistency**: `VERSION` file is the single source of truth. Hatchling reads it at build time; Python code uses `importlib.metadata.version("meridian-vpn")` at runtime. CI validates VERSION format (`^\d+\.\d+\.\d+$`).
- **Ecosystem cross-promotion**: Always upsell/reference related Meridian tools where contextually appropriate. When adding error messages, output, templates, issue templates, or docs — promote the relevant tool for that context. Current tools to cross-promote:
  - `meridian ping` / `meridian.msu.rocks/ping` — for connection issues, reachability testing
  - `meridian check` — for pre-deployment server validation
  - `meridian diagnostics` — for bug reports and server-side debugging
  - `meridian.msu.rocks` — for docs, setup guides, command builder
  - Connection info pages — for end-user onboarding and troubleshooting
  - The pattern: error/failure messages → suggest ping first (network issue?), then diagnostics (server issue?), then GitHub issues (bug?)
  - **Context-sensitive upsells**: don't blindly suggest every tool — only suggest the tool that helps for the specific failure mode. Example: if ping shows port 443 is blocked, suggesting `meridian diagnostics` doesn't help (it's a firewall issue). But if ping passes and VPN still fails, diagnostics is the right next step.
  - **Pre-fill URLs with known data**: when server IP and domain are available in context (templates, CLI output), always generate pre-filled `meridian.msu.rocks/ping?ip=...&domain=...` URLs so users land on a ready-to-run test.
- **CLI installation**: installed via `uv tool install meridian-vpn` (preferred) or `pipx install meridian-vpn`. Entry point is `meridian`. Location depends on the tool (typically `~/.local/bin/`).
- **Auto-update**: checks PyPI JSON API for latest version. Auto-upgrades patches via `uv tool upgrade` / `pipx upgrade`, prompts for minor/major. Uses `os.execvp()` to re-exec after auto-patch.
- **Auto-update direction**: only updates when remote version is strictly newer (`packaging.version.Version` comparison). Running a local dev build with a higher version will NOT trigger a downgrade.
- **`jinja2_native = True` in ansible.cfg**: required for `body_format: json` to send native integer types (e.g., `port`). Safe with mixed text+expression templates (`settings: >-` blocks) because Jinja2 NativeEnvironment only returns native types for single-expression templates. Do NOT remove without an alternative solution for integer typing.
- **`client list` bypasses Ansible**: uses direct curl + native Python JSON parsing for instant results instead of running a full playbook. `client add` and `client remove` still use Ansible playbooks because they modify state and benefit from idempotency.
- **Playbook bundling**: playbooks exist in two places — repo root (for CI/dev) and `src/meridian/playbooks/` (bundled in package). When editing playbooks, update both copies. A sync script or CI check should enforce this.
- **Credential management**: `ServerCredentials` dataclass in `credentials.py` replaces all `grep|awk|tr` YAML parsing. Handles special characters, preserves unknown fields, type-safe access.
- **When the user says "remember"**: save the instruction to this CLAUDE.md file so it persists across sessions. Don't use auto-memory — CLAUDE.md is the canonical place for project conventions.

## Documentation surfaces & update checklist

When adding or changing a feature, update ALL relevant surfaces. The source of truth for each type of information is marked with ★.

### Sources of truth

| Information | Source of Truth | Propagated To |
|---|---|---|
| **CLI commands & flags** | ★ `src/meridian/cli.py` (typer commands) | README.md commands table, docs/index.html builder, docs/ai/context.md CLI section, CLAUDE.md subcommands |
| **Architecture & modes** | ★ `CLAUDE.md` architecture section | docs/ai/architecture.md, docs/ai/context.md, README.md "How it works" |
| **SNI recommendations** | ★ `group_vars/all.yml` comments | docs/ai/troubleshooting.md SNI section, roles/output/templates/connection-summary.txt.j2 |
| **Troubleshooting guidance** | ★ `docs/ai/troubleshooting.md` | docs/index.html troubleshooting section, connection_issue.yml template |
| **App download links** | ★ `docs/index.html` apps section | 3x connection-info.html.j2 templates, README.md client apps table |
| **Version** | ★ `VERSION` file | `importlib.metadata` at runtime (hatchling reads VERSION at build), docs/version (CD sync) |
| **Error/failure guidance** | ★ `meridian` script `fail()` function | docs/ai/troubleshooting.md decision tree |

### Surface update checklist

When adding a **new subcommand**:
- [ ] `src/meridian/commands/newcmd.py` — implement `run()` function
- [ ] `src/meridian/cli.py` — add typer command + import
- [ ] `tests/test_cli.py` — add help smoke test
- [ ] `README.md` — add to commands table
- [ ] `docs/index.html` — add tab to command builder (if user-facing)
- [ ] `docs/ai/context.md` — add to CLI Commands section
- [ ] `CLAUDE.md` — add to meridian subcommands list
- [ ] Regenerate `docs/ai/reference.md` (cat context + architecture + troubleshooting)

When adding a **new flag to setup**:
- [ ] `src/meridian/commands/setup.py` — add parameter + logic
- [ ] `src/meridian/cli.py` — add `typer.Option` to setup_cmd
- [ ] `docs/index.html` — add checkbox/input to setup command builder
- [ ] `docs/ai/context.md` — add to setup flags list
- [ ] `CLAUDE.md` — update subcommands line
- [ ] `group_vars/all.yml` — add default variable with comment
- [ ] Regenerate `docs/ai/reference.md`

When adding a **new inbound/transport type**:
- [ ] `roles/xray/tasks/` — create/update inbound task
- [ ] `roles/xray/tasks/main.yml` — add include gate
- [ ] `roles/shared/tasks/generate_client_output.yml` — VLESS URL + QR codes
- [ ] `roles/output/tasks/main.yml` — terminal output (QR + URL display)
- [ ] `roles/output/templates/connection-summary.txt.j2` — admin summary
- [ ] `roles/output/templates/connection-summary-client.txt.j2` — client summary
- [ ] `roles/output/templates/connection-info.html.j2` — local HTML page
- [ ] `roles/caddy/templates/connection-info.html.j2` — server HTML page (+ QR gen in caddy/tasks/main.yml)
- [ ] `roles/caddy/tasks/main.yml` — build URL + generate QR on server
- [ ] `roles/client_management/tasks/main.yml` — discover inbound
- [ ] `roles/client_management/tasks/add_client.yml` — add client to inbound + terminal output
- [ ] `roles/client_management/tasks/remove_client.yml` — remove client from inbound
- [ ] `roles/xray/tasks/configure_panel.yml` — save setting to credentials
- [ ] `tests/render_templates.py` — add mock variables (templates are auto-discovered)
- [ ] `docs/ai/context.md` — update port table and architecture
- [ ] `docs/ai/architecture.md` — update topology diagrams
- [ ] Regenerate `docs/ai/reference.md`

When changing **SNI recommendations**:
- [ ] `group_vars/all.yml` — update "Good choices" / "Avoid" comments
- [ ] `roles/output/templates/connection-summary.txt.j2` — update alternatives line
- [ ] `docs/ai/troubleshooting.md` — update SNI Target Selection section
- [ ] Regenerate `docs/ai/reference.md`

When changing **troubleshooting/error guidance**:
- [ ] `docs/ai/troubleshooting.md` — update symptom/fix sections
- [ ] `docs/index.html` — update troubleshooting details section
- [ ] `.github/ISSUE_TEMPLATE/connection_issue.yml` — update pre-report checklist
- [ ] Regenerate `docs/ai/reference.md`

### Current inconsistencies to fix (tracked)

All previously tracked inconsistencies have been resolved:
- ~~`docs/index.html` command builder~~ — added `scan` tab, `--xhttp` checkbox, `--ai` mention, SNI guidance
- ~~`bug_report.yml` --rage~~ → fixed to "diagnostics output"
- ~~`CONTRIBUTING.md` --rage~~ → fixed to `meridian diagnostics`
- ~~`SECURITY.md` --rage~~ → fixed to `meridian diagnostics`
- ~~`README.md` missing scan/xhttp~~ → added to commands table
- i18n translations extracted to `docs/i18n.js` (index.html reduced from 805 to ~620 lines)

## CI/CD pipelines

**Pipeline chain:** push → CI → CD (on CI success) → Release (on CD success)

### CI (`.github/workflows/ci.yml`) — runs on push and PR
- **Lint**: `ansible/ansible-lint@main` — catches FQCN, YAML style, deprecated patterns
- **Python Test**: `pytest` on Python 3.10 + 3.12 — credentials, servers, CLI, ansible, update logic
- **Python Lint**: `ruff check` + `ruff format --check` — style, imports, formatting
- **Validate**: syntax check all playbooks + auto-discovered template rendering test with Ansible filter mocks
- **Shell**: `bash -n` + shellcheck on `install.sh` and `setup.sh` + VERSION format validation + `body_format` policy check + connection-info app link sync check
- **Dry run**: `ansible-playbook --check` with local connection (validates task structure)
- Skipped lint rules: `var-naming[no-role-prefix]` (would require renaming 90+ variables), `command-instead-of-module` (curl/dig used intentionally)

### CD (`.github/workflows/cd.yml`) — triggers after CI succeeds (workflow_run)
- Syncs `install.sh` → `docs/install.sh`, `setup.sh` → `docs/setup.sh`, `VERSION` → `docs/version`
- Generates `SHA256SUMS` checksum file for install scripts
- Auto-commits with `[skip ci]`
- Ensures `meridian.msu.rocks/` always serves the latest installer and version

## Versioning & releases

### Semver: X.Y.Z

| Bump | When | User experience |
|------|------|----------------|
| **Z** (patch) | Bug fixes, docs, safe tweaks | Auto-updated silently (next CLI run) |
| **Y** (minor) | New features, opt-in changes (e.g., `--xhttp`, `scan`) | Prompted: "Update available", user runs `self-update` |
| **X** (major) | Breaking changes, defaults change | Prompted: "Major update available", user runs `self-update` |

### How to release

1. Update `VERSION` file with the new version
2. Commit and push to main → three workflows trigger in chain:
   - **CI**: validates VERSION format, runs pytest + ruff + ansible-lint
   - **CD**: syncs install files to GitHub Pages (`meridian.msu.rocks/version`)
   - **Release**: creates git tag `vX.Y.Z` + GitHub Release + publishes to PyPI
3. Users on auto-patch get the update on next CLI run; others see "Update available" prompt

### When to bump (guidance for Claude)

After completing a feature or fix, **always bump the version as part of the commit workflow**:
- Fixed a bug or updated docs? → Bump Z (patch): `1.1.0` → `1.1.1`
- Added a new command, flag, or transport? → Bump Y (minor): `1.1.0` → `1.2.0`
- Changed defaults or broke backward compat? → Bump X (major): `1.2.0` → `2.0.0`

**Do NOT skip version bumps.** Every meaningful change to the CLI or playbooks should get a version bump (just edit the `VERSION` file) so users on auto-patch get fixes and users on manual update see the prompt. If multiple features are in one session, one version bump at the end is fine.

### Release artifacts

- **PyPI package**: `meridian-vpn` on PyPI (published by release workflow)
- **Version file**: `meridian.msu.rocks/version` (CD sync from VERSION)
- **Installer**: `meridian.msu.rocks/install.sh` (CD sync)
- **GitHub Release**: auto-created by `.github/workflows/release.yml` when VERSION changes

CI validates VERSION format (`^\d+\.\d+\.\d+$`) on every push.

## Backlog & tech debt

See `BACKLOG.md` for the full prioritized task list with completion status.

## GitHub community files

- `.github/ISSUE_TEMPLATE/bug_report.yml` — structured bug report with diagnostics prompt
- `.github/ISSUE_TEMPLATE/connection_issue.yml` — connection troubleshooting with --check prompt
- `.github/ISSUE_TEMPLATE/feature_request.yml` — feature requests by area
- `.github/ISSUE_TEMPLATE/config.yml` — disables blank issues, links to docs
- `SECURITY.md` — vulnerability reporting policy and security design overview
- `CONTRIBUTING.md` — development setup, PR guidelines, testing approach
