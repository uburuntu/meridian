# CLAUDE.md

## North-star vision

Meridian exists to make censorship-resistant VPN accessible to everyone. The core idea: a semi-technical person (who can rent a VPS and run commands) becomes the "tech friend" who shares secure VPN access with family, older relatives, and less technical people — via share links, QR codes, and guided connection pages.

**Audience (three tiers):**
1. **Tech friends** — set up a server, share keys with family and friends
2. **Power users** — need fast VPS rebuilds when IPs get blocked regularly
3. **Organizations** — NGOs, journalists, activists helping people in censored regions

**Design principles:**
- **Protocol-agnostic harness** — Meridian doesn't build protocols, it makes the best undetectable ones easy to deploy. Today that's VLESS+Reality; tomorrow it could be something else. The architecture must make swapping painless.
- **Guided wizard** — interactive setup that explains each choice but has smart defaults. First-time users learn; repeat users skip.
- **Guided handoff** — Meridian's responsibility ends at the server. Client setup is the user's job, but Meridian makes it effortless: polished connection pages with step-by-step instructions, app download links, QR codes, and shareable URLs.
- **Rebuild-fast** — IPs get blocked. Spinning up a fresh VPS and running `meridian setup` should get you back online in minutes, not hours.

## Project overview

Python CLI for deploying censorship-resistant proxy servers. Currently supports VLESS+Reality (standalone) with optional domain mode for CDN fallback (VLESS+WSS, VLESS+XHTTP). Server provisioning uses a pure-Python provisioner (`src/meridian/provision/`).

## Strategic direction

- **Keeping 3x-ui.** It's powerful, actively maintained, and the web UI keeps power users on Meridian. The coupling is contained in `PanelClient` — we strengthen that boundary, not replace it.
- **Output stack modernization.** Connection output is being refactored into focused modules: `urls.py` (URL building + QR), `render.py` (HTML/text files), `display.py` (terminal output). The legacy `output.py` facade remains during migration.
- **Protocol-agnostic architecture.** The provisioner's step pipeline and protocol registry are designed to make adding new transports straightforward — add an `InboundType`, create a `Protocol` subclass, add a provisioner step.

## Architecture

- **Standalone mode**: Single server with VLESS+Reality. Optional domain mode adds HAProxy (SNI routing), Caddy (TLS), and VLESS+WSS (CDN fallback via Cloudflare).
- Chain/relay mode (two-server relay for IP whitelist bypass) was extracted in v2.1. The protocol abstraction layer is designed to support relay chains when censors introduce whitelists.

### Key design decisions

- HAProxy on port 443 does TCP-level SNI routing without TLS termination, so both Reality and Caddy can coexist on port 443.
- 3x-ui panel is managed entirely via its REST API (no manual web UI steps).
- Caddy handles TLS automatically — email is optional, not required.
- Caddy config uses import pattern: Meridian writes to `/etc/caddy/conf.d/meridian.caddy`, main Caddyfile just has `import /etc/caddy/conf.d/*.caddy`. User's own Caddyfile is never overwritten.
- Credentials are persisted locally in `~/.meridian/credentials/<IP>/proxy.yml` for idempotent re-runs. Credentials are saved BEFORE changing the panel password to prevent lockout on failure.
- Uninstall deletes credentials from both server and local machine to prevent stale state on reinstall.
- Docker installation is skipped if Docker is already running with containers.
- In no-domain mode, the panel binds to localhost only (SSH tunnel required).
- 3x-ui Docker image is pinned to a tested version (`ProvisionContext.threexui_version` in `provision/steps.py`) to prevent API breakage.
- Secrets are handled via `shlex.quote()` and never logged to terminal.

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
  protocols.py             Protocol ABC + InboundType registry + concrete implementations (Reality, XHTTP, WSS)
  panel.py                 PanelClient: 3x-ui REST API wrapper via SSH (login, inbounds, clients, keys)
  output.py                Legacy facade (migrating to urls.py, render.py, display.py)
  models.py                Data models (Inbound, ProtocolURL)
  urls.py                  VLESS URL building and QR generation
  render.py                HTML/text file rendering
  display.py               Terminal output for connection info
  servers.py               ServerRegistry: list/find/add/remove
  ssh.py                   ServerConnection: run, check_ssh, detect_local_mode, tcp_connect
  update.py                Auto-update via PyPI (semver: auto-patch, prompt minor/major)
  ai.py                    AI prompt building, clipboard, bundled docs
  provision/               Pure-Python provisioner package
    __init__.py             build_setup_steps() pipeline assembly
    steps.py                ProvisionContext, Provisioner, Step, StepResult
    common.py               OS-level setup: packages, hardening, sysctl, firewall
    docker.py               Docker installation + 3x-ui container deployment
    panel.py                Panel configuration + login
    xray.py                 Inbound creation (Reality, XHTTP, WSS) + verification
    services.py             HAProxy + Caddy installation (domain mode)
    uninstall.py            Server cleanup + credential removal
  templates/               Package data
    connection-info.html.j2  Unified connection info page (all modes, i18n)
  data/                    Package data files
    ai-reference.md        Bundled AI reference docs (generated by make ai-docs)
  commands/                One module per subcommand
    resolve.py             Server resolution logic (shared by most commands)
    setup.py               Interactive wizard + provisioner execution
    client.py              client add/list/remove (via PanelClient)
    server.py              server add/list/remove
    check.py               Pre-flight validation (SNI, ports, DNS, OS, disk, clock)
    scan.py                RealiTLScanner download + execution + SNI selection
    ping.py                Reachability test (TCP, TLS, clock drift)
    diagnostics.py         System info collection + redaction
    uninstall.py           Provisioner execution + credential cleanup
Makefile                  Dev workflow: install, test, lint, ci, build, publish
docker-compose.test.yml   3x-ui container for integration tests
uv.lock                   Locked dependencies (committed)
install.sh                 CLI installer (bootstraps uv, installs from PyPI, migrates old bash CLI)
setup.sh                   Compat shim → installs CLI + forwards args
tests/
  test_cli.py              CliRunner smoke tests
  test_credentials.py      Credential dataclass tests
  test_servers.py          Server registry tests
  test_update.py           Version comparison + update throttle tests
  test_protocols.py        Protocol ABC + InboundType registry tests
  test_panel.py            PanelClient tests with mocked SSH
  test_output.py           VLESS URL building and output generation tests
  test_client.py           Client add/list/remove tests
  test_resolve.py          Server resolution logic tests (all 5 paths)
  test_console.py          Console confirm/fail/prompt tests
  test_setup.py            Setup wizard tests (IP detection, validation)
  test_ssh.py              SSH connection and tcp_connect tests
  test_integration_3xui.py 3x-ui Docker API round-trip (requires container)
  test_render_templates.py Jinja2 template rendering tests
  render_templates.py      Jinja2 template rendering validation (CI)
  conftest.py              Shared fixtures
docs/architecture.md       Mermaid architecture diagrams (CLI flow, modes, credentials, CI/CD)
docs/index.html            Website hosted on meridian.msu.rocks (GitHub Pages)
docs/ping.html             Web-based ping tool (server reachability test)
docs/CNAME                 Custom domain for GitHub Pages
.github/workflows/ci.yml   CI: pytest, ruff, mypy, shellcheck, template validation
.github/workflows/release.yml  Release: deploy Pages, git tag, GitHub Release, PyPI publish
SECURITY.md                Vulnerability reporting policy
CONTRIBUTING.md            Development setup and PR guidelines
```

## Implicit dependencies & cross-file relationships

These are easy to break by editing one file without updating the others:

### CLI architecture
- `meridian` CLI is a Python package (`meridian-vpn` on PyPI), installed via `uv tool install` or `pipx install`
- Built with typer (CLI framework) + rich (terminal output) + PyYAML (credential management)
- Data directory: `~/.meridian/` (credentials, cache, servers)
- Credentials cached locally in `~/.meridian/credentials/<IP>/` (per-server subdirectories)
- Server as source of truth: credentials stored at `/etc/meridian/` on the server (synced by provisioner)
- Server index: `~/.meridian/servers` (line-oriented: `host user name`, no spaces in names)
- Auto-update checks PyPI JSON API (throttled to 1x/60s); auto-patches via `uv tool upgrade` / `pipx upgrade`
- `VERSION` file at repo root is the single source of truth — read by hatchling at build time, by `importlib.metadata` at runtime
- `setup.sh` is a compat shim that installs the CLI and forwards args

### meridian CLI ↔ provisioner
- CLI creates `ProvisionContext` with user inputs and `ServerConnection` for SSH
- `build_setup_steps()` assembles the step pipeline
- `Provisioner.run()` executes steps sequentially, returns `list[StepResult]`
- Each step: `run(conn: ServerConnection, ctx: ProvisionContext) -> StepResult`
- Steps communicate via `ProvisionContext` typed fields + dict-like access
- Step pipeline: common → docker → panel → xray inbounds → services (HAProxy/Caddy/connection page)

### meridian subcommands
- `meridian setup [IP] [--domain --email --sni --xhttp --name --user --yes]` — deploy server
- `meridian client add|list|remove NAME [--server]` — manage clients via PanelClient
- `meridian server add|list|remove` — manage known servers
- `meridian check [IP] [--ai --server]` — pre-flight validation (SNI, ports, DNS, OS, disk, ASN)
- `meridian scan [IP] [--server]` — find optimal SNI targets via RealiTLScanner on server
- `meridian ping [IP] [--server]` — test proxy reachability from client device (no SSH needed)
- `meridian diagnostics [IP] [--ai --server]` — collect system info for bug reports
- `meridian uninstall [IP] [--server --yes]` — remove proxy from server
- `meridian self-update` — update CLI via `uv tool upgrade` / `pipx upgrade`
- `meridian version` — show version
- Most commands accept `--server NAME` to target a specific named server from the registry.

### docs/index.html ↔ meridian CLI
- Website command builder has tabbed interface generating `meridian` subcommands
- Install files served from `meridian.msu.rocks/` — synced by CD workflow: `install.sh`, `setup.sh`, `version`
- CLI itself distributed via PyPI (`meridian-vpn`), not served from website
- Website references the same app download links as `src/meridian/templates/connection-info.html.j2`
- `docs/ping.html` — standalone web ping tool, uses `fetch()` timing to test server reachability from browser. Supports URL params (`?ip=...&domain=...&name=...`) for shareable pre-filled links. Stores server history in localStorage.

### Connection info HTML template
- `src/meridian/templates/connection-info.html.j2` — unified template for all modes
- Uses `is_server_hosted` variable to toggle between server-hosted (Caddy) and local-saved output
- Uses `domain_mode` to toggle WSS backup card, `xhttp_enabled` for XHTTP card
- Server-hosted pages get usage stats JS; local pages don't
- QR codes: server-hosted uses `reality_qr_b64` (generated on server), local uses `reality_qr_b64_local` (generated locally)
- i18n (ru/fa/zh) via `data-t` attributes and inline JS translations
- `docs/demo.html` mirrors the same CSS/structure with static demo data
- CI checks app download links match between the template and `docs/demo.html`

### Credential flow
- **V2 format**: nested YAML with `version: 2`, sections: `panel`, `server`, `protocols`, `clients`
- V1 flat format is auto-migrated on load; next `save()` writes v2
- `None` means "not set" (distinct from empty string `""`)
- Server is source of truth: `/etc/meridian/proxy.yml` on the server
- Local cache: `~/.meridian/credentials/<IP>/proxy.yml` per server
- Clients are tracked inside the main `proxy.yml` under the `clients` list (no separate file)
- Domain is saved to credentials file (`server.domain`) for detection on re-runs
- CLI reads saved credentials to find the server IP (`server.ip`) for client/uninstall/diagnostics commands
- CLI fetches credentials from `/etc/meridian/` via SSH when not found locally (handles cross-machine runs)
- `meridian server add IP` fetches credentials from server, caches locally
- `ServerCredentials` dataclass provides typed access: `creds.panel.username`, `creds.server.sni`, `creds.reality.uuid`, etc.
- XHTTP presence is detected dynamically from the panel API inbound list

### Client management flow
- `meridian client add|list|remove` uses `PanelClient` (Python) for all API calls
- Client names map to 3x-ui `email` fields: `reality-{name}`, `wss-{name}`, `xhttp-{name}` (e.g., `reality-alice`, `wss-alice`, `xhttp-alice`)
- The first client created during setup uses `reality-default` — same naming convention
- Clients are tracked in the main `proxy.yml` under the `clients` list with UUIDs and timestamps
- 3x-ui API: `addClient` adds to existing inbound (id in form body), `delClient/{uuid}` removes by client UUID (NOT email — email silently succeeds but doesn't delete)
- `meridian client add`/`meridian client remove` resolve server IP from saved credentials or `--server` flag
- VLESS URLs, QR codes, HTML/text output generated by `urls.py`, `render.py`, `display.py`

### Protocol/inbound type registry
- `src/meridian/protocols.py` — `Protocol` ABC with concrete `RealityProtocol`, `XHTTPProtocol`, `WSSProtocol`
- Each protocol defines: `build_url()`, `client_settings()`, `find_inbound()`, `requires_domain`, `shares_uuid_with`
- `INBOUND_TYPES` dict maps key to `InboundType(remark, email_prefix, flow)` — sole source of truth for inbound types
- `PROTOCOLS` ordered list — Reality first (primary), then XHTTP, then WSS
- `available_protocols(inbounds, domain)` filters to what's active on this server
- Adding a new protocol: add `InboundType`, create `Protocol` subclass, append to `PROTOCOLS`, add provisioner step in `provision/xray.py`

### Caddy config pattern
- Meridian writes to `/etc/caddy/conf.d/meridian.caddy` (not the main Caddyfile)
- Main Caddyfile gets a single `import /etc/caddy/conf.d/*.caddy` line added
- Uninstall removes only `/etc/caddy/conf.d/meridian.caddy`, not the user's Caddyfile
- `meridian setup` interactive wizard checks saved credentials for domain suggestion

### Panel health check URL
- After first run, the panel root `/` returns 404 (webBasePath is set) — health check accepts 404 as "responsive"
- The panel needs a `docker restart` after changing `webBasePath` (setting doesn't apply live)

### Xray binary path
- Binary is at `/app/bin/xray-linux-*` inside the 3x-ui container (architecture-dependent)
- Discovered dynamically via `ls` glob
- x25519 output format: `PrivateKey:` and `Password:` (not `Private key:` / `Public key:` in newer Xray versions)
- Parsing uses regex with both old and new format patterns; assertion verifies keys were parsed

### Feedback loop
- `fail()` in meridian CLI suggests `meridian diagnostics` and links to GitHub issues
- Success output mentions feedback URL
- Website has troubleshooting with `meridian check` and `meridian diagnostics` commands
- README has troubleshooting section

## Key API patterns

- 3x-ui login: `POST /login` (form-urlencoded) returns session cookie. Login MUST use form-urlencoded (not JSON).
- All other API calls use JSON bodies.
- Add inbound: `POST /panel/api/inbounds/add`. The `settings`, `streamSettings`, `sniffing` fields must be JSON **strings** (not nested objects). The Go struct uses `string` type for these fields.
- List inbounds: `GET /panel/api/inbounds/list` (check by remark before creating)
- 3x-ui rejects duplicate ports — two inbounds cannot share the same port. XHTTP needs its own dedicated port separate from Reality TCP.
- Update settings: `POST /panel/setting/update` (JSON body)
- Update credentials: `POST /panel/setting/updateUser` (JSON body)
- Read settings: `POST /panel/setting/all`
- Xray template config: set `xrayTemplateConfig` field in `/panel/setting/update`
- Key generation: `docker exec 3x-ui sh -c '/app/bin/xray-linux-* x25519'` (parse PrivateKey/Password lines), `docker exec 3x-ui sh -c '/app/bin/xray-linux-* uuid'`

## Build and test

```bash
# Install CLI in editable mode with dev dependencies (uses uv sync --extra dev)
make install

# Run full CI locally (lint + format + test + templates)
make ci

# Individual targets:
make test              # pytest
make lint              # ruff check
make format-check      # ruff format --check
make typecheck         # mypy
make templates         # Jinja2 template rendering test

# To fully test, import the VLESS URL into v2rayNG and check connectivity.
```


## Conventions

- QR codes generated with `qrencode` — must be installed on the local machine
- Cross-platform: `base64 | tr -d '\n'` instead of `base64 -w0` (macOS compat)
- XHTTP transport doesn't support `xtls-rprx-vision` flow (must be empty string)
- `reality_dest` is derived from `reality_sni` (`{sni}:443`) — don't hardcode separately
- Docker role removes conflicting `docker.io` / `containerd` / `runc` packages only when `docker-ce` is not already installed AND no containers are running
- **SNI target selection**: Never recommend apple.com or icloud.com (Apple-owned ASN — mismatch with VPS hosting is instantly detectable). Good choices: www.microsoft.com, www.twitch.tv, dl.google.com, github.com (global CDN, shared infrastructure). Best: run `meridian scan` for same-network targets.
- **Always use context7 MCP to check up-to-date docs** before writing or modifying code that depends on external tools/libraries (Docker, Caddy, GitHub Actions, shellcheck, etc.) — stale patterns and outdated common knowledge cause real deployment failures. Don't rely on training data for API syntax, CLI flags, or workflow configuration — verify against current docs first.
- **curl|bash stdin trap**: in `install.sh` and `setup.sh` (compat shim), any command that reads stdin MUST have `</dev/null` — the `meridian` CLI runs directly so this isn't needed there, but `</dev/null` on SSH commands is still good practice
- **pip3 install on modern Debian/Ubuntu**: must handle PEP 668 "externally managed environment" — try pipx, then `--user`, then `--break-system-packages`, then apt
- **pip user bin PATH**: after pip3 install --user, add `~/.local/bin` (Linux) and `~/Library/Python/*/bin` (macOS) to PATH
- **meridian interactive prompts**: `console.prompt()` reads from `/dev/tty` for pipe safety; detect public IPv4 with `curl -4` to avoid IPv6; suggest domain from saved credentials
- **console output functions**: `info()`, `ok()`, `warn()`, `fail()` use Rich markup — pass plain text, not ANSI codes. `fail()` raises `typer.Exit(1)` and is testable with CliRunner.
- **GitHub raw CDN caching**: raw.githubusercontent.com caches for ~60-120s; can't bust with query params or headers, just wait. Serving from meridian.msu.rocks avoids this.
- **HAProxy health checks**: do NOT use `check` on TLS backends (Caddy, Xray) — TCP probes fail on TLS-only ports, causing "backend has no server available" errors. These are local systemd services, not load-balanced pools.
- **docs/ deploy**: `docs/` source files are committed to git. At deploy time, the Release workflow builds `_site/` by copying `docs/` + `install.sh` + `setup.sh` + `VERSION` (as `version`) + `SHA256SUMS` + `ai/reference.md`. Deployed via `actions/deploy-pages` artifact (no git commits for synced files).
- **AI docs**: Source files in `docs/ai/` (`context.md`, `architecture.md`, `troubleshooting.md`). `make ai-docs` concatenates them into `src/meridian/data/ai-reference.md` (bundled in package). `make build` runs this automatically. Edit the source files, not `reference.md`. The deploy workflow also generates `ai/reference.md` for the website.
- **`--ai` flag**: `meridian check --ai` and `meridian diagnostics --ai` bundle AI docs + command output into a clipboard-ready prompt for ChatGPT/Claude. Docs are loaded from bundled package data via `importlib.resources` (no network fetch or cache).
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
- **`client add/remove/list` use PanelClient directly**: All client operations go through `PanelClient` (Python class wrapping 3x-ui REST API via SSH curl). This gives instant results.
- **PanelClient API patterns**: Login uses form-urlencoded (URL-encoded). Inbound/client operations use JSON. The `settings` field is a JSON STRING inside the JSON body (3x-ui Go struct quirk). Remove client by UUID (not email — email silently fails).
- **Credential management**: `ServerCredentials` dataclass in `credentials.py` uses v2 nested format: `panel`, `server`, `protocols` (dict of protocol dataclasses), `clients` (list). V1 flat format is auto-migrated on load. Access via `creds.panel.username`, `creds.server.sni`, `creds.reality.uuid`, etc. `None` = "not set" (distinct from `""`). Handles special characters, preserves unknown fields, type-safe access.
- **When the user says "remember"**: save the instruction to this CLAUDE.md file so it persists across sessions. Don't use auto-memory — CLAUDE.md is the canonical place for project conventions.
- **Non-root on-server execution**: When a non-root user runs meridian on the server itself, `detect_local_mode()` sets `local_mode=True` + `needs_sudo=True`. Commands run via `sudo -n bash -c '...'`, credentials are copied via `sudo -n cat`. The `ResolvedServer.creds_dir` stays in `~/.meridian/credentials/<IP>/` (not `/etc/meridian/` which is root-only). This avoids the old hard-fail that forced users to type `sudo meridian` for every command.
- **`sudo meridian` on servers**: `install.sh` creates a symlink `/usr/local/bin/meridian → ~/.local/bin/meridian` via `sudo -n` (non-interactive, no password prompt). `self-update` in `update.py` refreshes the symlink if it already exists. This ensures `sudo meridian` works without `secure_path` issues.
- **`.bashrc` interactivity guard**: On Debian/Ubuntu, `.bashrc` has `case $- in *i*) ;; *) return;; esac` near the top. Anything appended AFTER this guard is unreachable for non-interactive shells (`ssh host 'cmd'`). `install.sh` PREPENDS the PATH export before the guard using `mktemp` + `cat` + `mv`. Idempotency uses a `# Meridian CLI` marker (not dir string match, which false-positives on uv's env line).
- **Shell injection in `conn.run()`**: ALL values interpolated into shell command strings passed to `conn.run()` MUST use `shlex.quote()`. This is critical because `needs_sudo` escalates commands to root via `sudo -n bash -c`. Affected files: `client.py` (credentials), `check.py` (SNI/domain), `diagnostics.py` (domain), `scan.py` (URL/CIDR), `ping.py` (SNI/IP). The shared `ssh.tcp_connect()` has quoting built in.
- **Shared utilities in `ssh.py`**: `tcp_connect(host, port, timeout)` is the single source of truth for TCP connectivity tests (with `shlex.quote` built in). Used by both `check.py` and `ping.py`. Don't create local `_tcp_connect` copies.
- **Cookie file for `client list`**: The curl cookie jar for 3x-ui API auth lives at `$HOME/.meridian/.cookie` (not `/tmp/.mc`). The old `/tmp` location was world-readable — race condition on multi-user servers.
- **`_is_on_server()` caveats**: Uses `curl ifconfig.me` which can false-positive behind NAT (laptop and server share public IP) or if ifconfig.me is spoofed. When this triggers `needs_sudo`, commands run as root on the local machine. A local interface check would be more robust but isn't implemented yet.
- **Integration tests**: `tests/test_integration_3xui.py` requires a running 3x-ui Docker container (`docker-compose.test.yml`). Auto-skipped when container isn't running. CI has a separate `integration` job. The `python-test` job explicitly `--ignore`s this file.
- **Mermaid architecture diagrams**: `docs/architecture.md` has Mermaid diagrams for CLI flow, privilege escalation, all deployment modes, credential lifecycle, client management, install/PATH, and CI/CD. Update when architecture changes.
- **ty (Astral type checker)**: Evaluated but not adopted -- pre-1.0, has false positives on method name shadowing (`ServerRegistry.list` shadows builtin `list`). Revisit when ty reaches 1.0. mypy runs in CI (`make typecheck`).

## Documentation surfaces & update checklist

When adding or changing a feature, update ALL relevant surfaces. The source of truth for each type of information is marked with ★.

### Sources of truth

| Information | Source of Truth | Propagated To |
|---|---|---|
| **CLI commands & flags** | ★ `src/meridian/cli.py` (typer commands) | README.md commands table, docs/index.html builder, docs/ai/context.md CLI section, CLAUDE.md subcommands |
| **Architecture & modes** | ★ `CLAUDE.md` architecture section | docs/ai/architecture.md, docs/ai/context.md, README.md "How it works" |
| **SNI recommendations** | ★ `CLAUDE.md` conventions section | docs/ai/troubleshooting.md SNI section |
| **Troubleshooting guidance** | ★ `docs/ai/troubleshooting.md` | docs/index.html troubleshooting section, connection_issue.yml template |
| **App download links** | ★ `docs/index.html` apps section | `src/meridian/templates/connection-info.html.j2`, docs/demo.html, README.md client apps table |
| **Version** | ★ `VERSION` file | `importlib.metadata` at runtime (hatchling reads VERSION at build), `version` in Pages deploy artifact |
| **Error/failure guidance** | ★ `src/meridian/console.py` `fail()` function | docs/ai/troubleshooting.md decision tree |

### Surface update checklist

When adding a **new subcommand**:
- [ ] `src/meridian/commands/newcmd.py` — implement `run()` function
- [ ] `src/meridian/cli.py` — add typer command + import
- [ ] `tests/test_cli.py` — add help smoke test
- [ ] `README.md` — add to commands table
- [ ] `docs/index.html` — add tab to command builder (if user-facing)
- [ ] `docs/ai/context.md` — add to CLI Commands section
- [ ] `CLAUDE.md` — add to meridian subcommands list
- [ ] Regenerate AI docs (`make ai-docs`)

When adding a **new flag to setup**:
- [ ] `src/meridian/commands/setup.py` — add parameter + logic
- [ ] `src/meridian/cli.py` — add `typer.Option` to setup_cmd
- [ ] `docs/index.html` — add checkbox/input to setup command builder
- [ ] `docs/ai/context.md` — add to setup flags list
- [ ] `CLAUDE.md` — update subcommands line
- [ ] Regenerate AI docs (`make ai-docs`)

When adding a **new inbound/transport type**:
- [ ] `src/meridian/protocols.py` — add `InboundType` entry + `Protocol` subclass + append to `PROTOCOLS`
- [ ] `src/meridian/provision/xray.py` — add inbound creation step
- [ ] `src/meridian/provision/__init__.py` — add step to pipeline
- [ ] `src/meridian/urls.py` — add URL building logic
- [ ] `src/meridian/render.py` — update HTML/text rendering
- [ ] `src/meridian/display.py` — update terminal output
- [ ] `src/meridian/templates/connection-info.html.j2` — add card for new transport
- [ ] `tests/test_protocols.py` — add test for new type
- [ ] `tests/render_templates.py` — add mock variables (templates are auto-discovered)
- [ ] `docs/ai/context.md` — update port table and architecture
- [ ] `docs/ai/architecture.md` — update topology diagrams
- [ ] Regenerate AI docs (`make ai-docs`)

When changing **SNI recommendations**:
- [ ] `CLAUDE.md` — update conventions section
- [ ] `docs/ai/troubleshooting.md` — update SNI Target Selection section
- [ ] Regenerate AI docs (`make ai-docs`)

When changing **troubleshooting/error guidance**:
- [ ] `docs/ai/troubleshooting.md` — update symptom/fix sections
- [ ] `docs/index.html` — update troubleshooting details section
- [ ] `.github/ISSUE_TEMPLATE/connection_issue.yml` — update pre-report checklist
- [ ] Regenerate AI docs (`make ai-docs`)

### Current inconsistencies to fix (tracked)

All previously tracked inconsistencies have been resolved:
- ~~`docs/index.html` command builder~~ — added `scan` tab, `--xhttp` checkbox, `--ai` mention, SNI guidance
- ~~`bug_report.yml` --rage~~ → fixed to "diagnostics output"
- ~~`CONTRIBUTING.md` --rage~~ → fixed to `meridian diagnostics`
- ~~`SECURITY.md` --rage~~ → fixed to `meridian diagnostics`
- ~~`README.md` missing scan/xhttp~~ → added to commands table
- i18n translations extracted to `docs/i18n.js` (index.html reduced from 805 to ~620 lines)

## CI/CD pipelines

**Pipeline chain:** push → CI → Release+Deploy (on CI success)

### CI (`.github/workflows/ci.yml`) — runs on push and PR
- **Python Test**: `pytest` on Python 3.10 + 3.12 — credentials, servers, CLI, update logic, protocols, panel, output
- **Python Lint**: `ruff check` + `ruff format --check` — style, imports, formatting
- **Type Check**: `mypy` — static type analysis with `types-PyYAML` stubs
- **Validate**: template rendering test + connection-info app link sync check + VERSION format validation
- **Shell**: `bash -n` + shellcheck on `install.sh` and `setup.sh`
- **Integration**: 3x-ui Docker container API round-trip tests

### Release (`.github/workflows/release.yml`) — triggers after CI succeeds (workflow_run)
- **Deploy Pages**: builds `_site/` from `docs/` + root install scripts, deploys via `actions/deploy-pages` artifact (no git commits)
- **Release**: checks if VERSION changed → creates git tag `vX.Y.Z` + GitHub Release
- **Publish**: builds wheel + publishes to PyPI via trusted publisher
- GitHub Pages source must be set to "GitHub Actions" in repo settings

## Versioning & releases

### Semver: X.Y.Z

| Bump | When | User experience |
|------|------|----------------|
| **Z** (patch) | Bug fixes, docs, safe tweaks | Auto-updated silently (next CLI run) |
| **Y** (minor) | New features, opt-in changes (e.g., `--xhttp`, `scan`) | Prompted: "Update available", user runs `self-update` |
| **X** (major) | Breaking changes, defaults change | Prompted: "Major update available", user runs `self-update` |

### How to release

1. Update `VERSION` file with the new version
2. Commit and push to main → two workflows trigger in chain:
   - **CI**: validates VERSION format, runs pytest + ruff + mypy
   - **Release**: deploys Pages, creates git tag `vX.Y.Z` + GitHub Release + publishes to PyPI
3. Users on auto-patch get the update on next CLI run; others see "Update available" prompt

### When to bump (guidance for Claude)

After completing a feature or fix, **always bump the version as part of the commit workflow**:
- Fixed a bug or updated docs? → Bump Z (patch): `1.1.0` → `1.1.1`
- Added a new command, flag, or transport? → Bump Y (minor): `1.1.0` → `1.2.0`
- Changed defaults or broke backward compat? → Bump X (major): `1.2.0` → `2.0.0`

**Do NOT skip version bumps.** Every meaningful change to the CLI or provisioner should get a version bump (just edit the `VERSION` file) so users on auto-patch get fixes and users on manual update see the prompt. If multiple features are in one session, one version bump at the end is fine.

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
