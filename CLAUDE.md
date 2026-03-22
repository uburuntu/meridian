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
- **Rebuild-fast** — IPs get blocked. Spinning up a fresh VPS and running `meridian deploy` should get you back online in minutes, not hours.

## Project overview

Python CLI for deploying censorship-resistant proxy servers. Supports VLESS+Reality (primary) with XHTTP (enhanced stealth, enabled by default) and optional domain mode for CDN fallback (VLESS+WSS). Server provisioning uses a pure-Python provisioner (`src/meridian/provision/`).

## Strategic direction

- **Keeping 3x-ui.** Powerful, actively maintained, web UI keeps power users. Coupling contained in `PanelClient`.
- **Output stack modernization.** Refactored into `urls.py` (URL building + QR), `render.py` (HTML/text files), `display.py` (terminal output). Legacy `output.py` facade remains during migration.
- **Protocol-agnostic architecture.** Step pipeline + protocol registry make adding transports straightforward.

## Architecture

- **All modes** deploy HAProxy (port 443, SNI routing) + Caddy (port 80/8443, TLS + web serving). In standalone mode (no domain), Caddy requests a Let's Encrypt IP certificate via ACME `shortlived` profile (6-day validity, auto-renewed). Falls back to self-signed if IP cert issuance is not supported. In domain mode, Caddy also handles VLESS+WSS (CDN fallback via Cloudflare).
- **XHTTP runs behind Caddy** on 127.0.0.1 (localhost only). Caddy reverse-proxies to it and handles TLS. No extra firewall port needed. Uses `security=tls` (Caddy's cert), path-based routing on port 443. Follows the same pattern as WSS.
- Chain/relay mode (two-server relay for IP whitelist bypass) was extracted in v2.1. The protocol abstraction layer supports relay chains when censors introduce whitelists.

### Key design decisions

- **HAProxy SNI routing**: port 443, TCP-level SNI inspection without TLS termination, so Reality and Caddy coexist on 443.
- **XHTTP behind Caddy (v3.6.0)**: XHTTP was moved from a separate Reality+XHTTP inbound on an external port to running behind Caddy on 127.0.0.1, matching WSS's architecture. Rationale: (1) community best practice is to keep external ports to 80/443 only (ntc.party, XTLS GitHub discussions); (2) NDSS 2025 cross-layer RTT paper shows no detection benefit from Reality TLS on XHTTP vs standard TLS behind Caddy; (3) simpler URLs (no Reality params), no extra firewall port; (4) XHTTP becomes a free fallback — enabled by default with zero stealth cost.
- **Caddy config import pattern**: writes to `/etc/caddy/conf.d/meridian.caddy`, main Caddyfile just has `import /etc/caddy/conf.d/*.caddy`. User's own Caddyfile is never overwritten.
- **Credential lockout prevention**: credentials saved BEFORE changing panel password.
- **3x-ui managed via REST API** — no manual web UI steps. Docker image pinned to tested version (`ProvisionContext.threexui_version`).
- **Panel access**: HTTPS on a secret path (reverse-proxied by Caddy) — no SSH tunnel required.
- **Docker skip**: installation skipped if Docker is already running with containers.
- **Secrets**: handled via `shlex.quote()` and never logged to terminal.

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
docs/index.html            Legacy website (being replaced by website/ Astro project on getmeridian.org)
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
- Built with typer + rich + PyYAML. Data directory: `~/.meridian/` (credentials, cache, servers)
- Credentials: local cache at `~/.meridian/credentials/<IP>/proxy.yml`, server source of truth at `/etc/meridian/proxy.yml`
- Server index: `~/.meridian/servers` (line-oriented: `host user name`, no spaces in names)
- Auto-update checks PyPI JSON API (throttled to 1x/60s); auto-patches via `uv tool upgrade` / `pipx upgrade`
- `VERSION` file is the single source of truth — read by hatchling at build time, by `importlib.metadata` at runtime

### meridian CLI ↔ provisioner
- CLI creates `ProvisionContext` with user inputs and `ServerConnection` for SSH
- `build_setup_steps()` assembles the step pipeline; `Provisioner.run()` executes sequentially
- Steps communicate via `ProvisionContext` typed fields + dict-like access
- Pipeline: common → docker → panel → xray inbounds → services (HAProxy/Caddy/connection page)

### meridian subcommands
- `meridian deploy [IP] [--domain --email --sni --xhttp --name --user --yes]` — deploy server. Wizard offers inline scan for camouflage target (SNI). Deploy summary uses Rich Panel.
- `meridian client add|list|remove NAME [--server]` — manage clients via PanelClient
- `meridian server add|list|remove` — manage known servers
- `meridian preflight [IP] [--ai --server]` — pre-flight validation (SNI, ports, DNS, OS, disk, ASN)
- `meridian scan [IP] [--server]` — find optimal camouflage targets via RealiTLScanner on server
- `meridian test [IP] [--server]` — test proxy reachability from client device (no SSH needed)
- `meridian doctor [IP] [--ai --server]` — collect system info for bug reports (alias: `rage`)
- `meridian teardown [IP] [--server --yes]` — remove proxy from server
- `meridian update` — update CLI via `uv tool upgrade` / `pipx upgrade`
- `meridian --version` / `meridian -v` — show version
- Most commands accept `--server NAME` to target a named server from the registry.

### Connection info HTML template
- `src/meridian/templates/connection-info.html.j2` — unified template for all modes
- `is_server_hosted` toggles server-hosted (Caddy) vs local-saved output
- `domain_mode` toggles WSS backup card, `xhttp_enabled` for XHTTP card
- QR codes: server-hosted uses `reality_qr_b64`, local uses `reality_qr_b64_local`
- i18n (ru/fa/zh) via `data-t` attributes and inline JS translations
- `docs/demo.html` mirrors same CSS/structure. CI checks app download links match.

### Credential flow
- **V2 format**: nested YAML with `version: 2`, sections: `panel`, `server`, `protocols`, `clients`
- V1 flat format auto-migrated on load; next `save()` writes v2. `None` = "not set" (distinct from `""`)
- Server is source of truth: `/etc/meridian/proxy.yml`. Local cache: `~/.meridian/credentials/<IP>/proxy.yml`
- `ServerCredentials` dataclass: `creds.panel.username`, `creds.server.sni`, `creds.reality.uuid`, `creds.xhttp.xhttp_path`, etc.
- CLI fetches credentials from `/etc/meridian/` via SSH when not found locally (cross-machine runs)
- XHTTP presence detected dynamically from panel API inbound list

### Client management flow
- Client names map to 3x-ui `email` fields: `reality-{name}`, `wss-{name}`, `xhttp-{name}`
- 3x-ui API: `addClient` adds to existing inbound, `delClient/{uuid}` removes by client UUID (NOT email — email silently succeeds but doesn't delete)
- VLESS URLs, QR codes, HTML/text output generated by `urls.py`, `render.py`, `display.py`

### Protocol/inbound type registry
- `protocols.py` — `Protocol` ABC with `RealityProtocol`, `XHTTPProtocol`, `WSSProtocol`
- `INBOUND_TYPES` dict maps key to `InboundType(remark, email_prefix, flow)` — sole source of truth
- `PROTOCOLS` ordered dict — Reality first (primary), then XHTTP, then WSS
- Adding a new protocol: add `InboundType`, create `Protocol` subclass, append to `PROTOCOLS`, add provisioner step

### Caddy config pattern
- Meridian writes to `/etc/caddy/conf.d/meridian.caddy` (not the main Caddyfile)
- Uninstall removes only `/etc/caddy/conf.d/meridian.caddy`, not the user's Caddyfile

### Panel & Xray internals
- Panel health check: root `/` returns 404 (webBasePath set) — 404 = "responsive". Needs `docker restart` after changing `webBasePath`.
- Xray binary: `/app/bin/xray-linux-*` in container, discovered via `ls` glob. x25519 output: `PrivateKey:` and `Password:` (regex with old+new format).

## Key API patterns

- 3x-ui login: `POST /login` (form-urlencoded). Login MUST use form-urlencoded (not JSON).
- All other API calls use JSON bodies.
- Add inbound: `POST /panel/api/inbounds/add`. The `settings`, `streamSettings`, `sniffing` fields must be JSON **strings** (not nested objects — 3x-ui Go struct quirk).
- List inbounds: `GET /panel/api/inbounds/list` (check by remark before creating)
- 3x-ui rejects duplicate ports — XHTTP needs its own dedicated port (internal, 127.0.0.1) separate from Reality TCP.
- Key generation: `docker exec 3x-ui sh -c '/app/bin/xray-linux-* x25519'` (parse PrivateKey/Password), `docker exec 3x-ui sh -c '/app/bin/xray-linux-* uuid'`

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

### Protocol & transport conventions
- XHTTP transport doesn't support `xtls-rprx-vision` flow (must be empty string)
- **XHTTP behind Caddy**: XHTTP port is internal only (127.0.0.1), no UFW rule needed. Xray config uses `security: none` (Caddy handles TLS). `xhttp_path` stored in credentials (`creds.xhttp.xhttp_path`). URL format: `vless://UUID@host:443?security=tls&type=xhttp&path=/xhttp_path`
- `reality_dest` is derived from `reality_sni` (`{sni}:443`) — don't hardcode separately
- **Camouflage target selection** (user-facing term for SNI): Never recommend apple.com or icloud.com (Apple-owned ASN — mismatch with VPS hosting is instantly detectable). Good: www.microsoft.com, www.twitch.tv, dl.google.com, github.com (global CDN). Best: run `meridian scan` for same-network targets.
- **HAProxy health checks**: do NOT use `check` on TLS backends — TCP probes fail on TLS-only ports.

### Build & deployment conventions
- QR codes generated with `qrencode` — must be installed on the local machine
- Cross-platform: `base64 | tr -d '\n'` instead of `base64 -w0` (macOS compat)
- Docker role removes conflicting packages only when `docker-ce` is not installed AND no containers are running
- **Always use context7 MCP to check up-to-date docs** before writing code that depends on external tools/libraries — stale patterns cause deployment failures.
- **curl|bash stdin trap**: in `install.sh` and `setup.sh`, any command reading stdin MUST have `</dev/null`
- **pip3 on modern Debian/Ubuntu**: handle PEP 668 — try pipx, then `--user`, then `--break-system-packages`, then apt
- **docs/ deploy**: Release workflow builds `_site/` from `docs/` + install scripts + VERSION + SHA256SUMS + ai/reference.md. No git commits.
- **AI docs**: Source in `docs/ai/`. `make ai-docs` concatenates into `src/meridian/data/ai-reference.md`. Edit sources, not reference.md.
- **Pre-push hook**: `.githooks/pre-push` runs 11 fast checks (~7s). Install with `make hooks`.

### CLI & console conventions
- **console output functions**: `info()`, `ok()`, `warn()`, `fail()` use Rich markup — pass plain text, not ANSI codes. `fail()` raises `typer.Exit(1)`.
- **meridian interactive prompts**: `console.prompt()` reads from `/dev/tty` for pipe safety; detect public IPv4 with `curl -4` to avoid IPv6
- **CLI installation**: `uv tool install meridian-vpn` (preferred) or `pipx install meridian-vpn`. Entry point: `meridian`.
- **Auto-update**: auto-patches via `uv tool upgrade`, prompts for minor/major. Uses `os.execvp()` to re-exec. Only updates when remote is strictly newer (no downgrade).
- **VERSION consistency**: `VERSION` file is the single source of truth. CI validates format (`^\d+\.\d+\.\d+$`).

### Security conventions
- **Shell injection in `conn.run()`**: ALL interpolated values MUST use `shlex.quote()`. Critical because `needs_sudo` escalates to root.
- **Cookie file for `client list`**: curl cookie jar at `$HOME/.meridian/.cookie` (not `/tmp/.mc`).

### Server execution conventions
- **Non-root on-server**: `detect_local_mode()` sets `local_mode=True` + `needs_sudo=True`. Commands run via `sudo -n bash -c '...'`.
- **`sudo meridian`**: `install.sh` creates symlink `/usr/local/bin/meridian -> ~/.local/bin/meridian` via `sudo -n`.
- **`.bashrc` interactivity guard**: `install.sh` PREPENDS PATH export before the `case $- in *i*)` guard using `mktemp` + `cat` + `mv`.

### Ecosystem cross-promotion
- Error/failure flow: suggest `meridian test` first (network?), then `meridian doctor` (server?), then GitHub issues (bug?)
- **Context-sensitive**: only suggest the tool that helps for the specific failure mode.
- **Pre-fill URLs**: generate `getmeridian.org/ping?ip=...&domain=...` when IP/domain available.

### Misc conventions
- **When the user says "remember"**: save the instruction to this CLAUDE.md file. Don't use auto-memory.
- **Integration tests**: `tests/test_integration_3xui.py` requires running 3x-ui Docker container. Auto-skipped when not running.
- **Mermaid diagrams**: `docs/architecture.md` — update when architecture changes.
- **PanelClient**: Login form-urlencoded. Settings field is JSON STRING inside JSON body. Remove client by UUID (not email).
- **Credential management**: v2 nested format with auto-migration from v1. `None` = not set. Preserves unknown fields via `_extra`.

## Documentation surfaces & update checklist

Sources of truth are marked with ★.

| Information | Source of Truth | Propagated To |
|---|---|---|
| **CLI commands & flags** | ★ `src/meridian/cli.py` | README.md, docs/index.html, docs/ai/context.md, CLAUDE.md |
| **Architecture & modes** | ★ `CLAUDE.md` architecture section | docs/ai/architecture.md, docs/ai/context.md, README.md |
| **SNI recommendations** | ★ `CLAUDE.md` conventions section | docs/ai/troubleshooting.md |
| **Troubleshooting** | ★ `docs/ai/troubleshooting.md` | docs/index.html, connection_issue.yml |
| **App download links** | ★ `docs/index.html` apps section | connection-info.html.j2, docs/demo.html, README.md |
| **Version** | ★ `VERSION` file | importlib.metadata, Pages deploy, docs/index.html, CHANGELOG.md |
| **Error guidance** | ★ `src/meridian/console.py` `fail()` | docs/ai/troubleshooting.md |

### Surface update checklists

**New subcommand**: implement in `commands/`, register in `cli.py`, add test in `test_cli.py`, update README.md, docs/index.html, docs/ai/context.md, CLAUDE.md subcommands, run `make ai-docs`.

**New flag to deploy**: add to `commands/setup.py` + `cli.py`, update docs/index.html builder, docs/ai/context.md, CLAUDE.md, run `make ai-docs`.

**New inbound/transport type**: add `InboundType` + `Protocol` subclass in `protocols.py`, add provisioner step in `xray.py` + `__init__.py`, update `urls.py`, `render.py`, `display.py`, `connection-info.html.j2`, add tests, update docs/ai, run `make ai-docs`.

**SNI recommendations**: update CLAUDE.md conventions + docs/ai/troubleshooting.md, run `make ai-docs`.

**Troubleshooting/error guidance**: update docs/ai/troubleshooting.md, docs/index.html, connection_issue.yml, run `make ai-docs`.

## CI/CD pipelines

**Pipeline chain:** push → CI → Release+Deploy (on CI success)

### CI (`.github/workflows/ci.yml`) — runs on push and PR
- **Python Test**: pytest on Python 3.10 + 3.12
- **Python Lint**: ruff check + ruff format --check
- **Type Check**: mypy with `types-PyYAML` stubs
- **Validate**: template rendering + app link sync + VERSION format
- **Shell**: bash -n + shellcheck on install.sh and setup.sh
- **Integration**: 3x-ui Docker API round-trip tests

### Release (`.github/workflows/release.yml`) — triggers after CI succeeds
- **Deploy Pages**: builds `_site/`, deploys via `actions/deploy-pages` artifact
- **Release**: creates git tag + GitHub Release (notes from CHANGELOG.md)
- **Publish**: builds wheel + publishes to PyPI via trusted publisher

## Versioning & releases

### Semver: X.Y.Z

| Bump | When | User experience |
|------|------|----------------|
| **Z** (patch) | Bug fixes, docs, safe tweaks | Auto-updated silently |
| **Y** (minor) | New features, opt-in changes | Prompted, user runs `update` |
| **X** (major) | Breaking changes, defaults change | Prompted, user runs `update` |

### How to release

1. Update `VERSION` + add CHANGELOG.md `## [X.Y.Z]` section
2. Commit and push to main → CI → Release (tag + GitHub Release + PyPI)

### When to bump (guidance for Claude)

After completing a feature or fix, **always bump the version**: patch for fixes/docs, minor for new features, major for breaking changes. Edit `VERSION` + add CHANGELOG.md entry. CI validates both. If multiple features in one session, one bump at the end is fine.

### Release artifacts

- **PyPI**: `meridian-vpn` (published by release workflow)
- **Website**: `getmeridian.org/version` (CD sync), `getmeridian.org/install.sh`
- **GitHub Release**: auto-created when VERSION changes, notes from CHANGELOG.md

## Codified patterns (follow at scale)

### 1. Protocol registry — single source of truth for transports
Cross-cutting concerns must have a single registry that downstream code iterates generically. Never hardcode protocol-specific branching — add to the registry and let consumers loop. Exemplified by `INBOUND_TYPES` + `PROTOCOLS` in `protocols.py`.

### 2. Credential lockout prevention — safety-critical ordering
Persist new secrets locally BEFORE issuing remote changes. Document with `# SAFETY` comment. Exemplified by `ConfigurePanel` in `provision/panel.py`.

### 3. Versioned data formats with auto-migration
Include auto-migration from previous versions. Preserve unknown fields in `_extra`. `save()` always writes latest version. Exemplified by v1→v2 credential migration.

### 4. Step pipeline — composable and independently testable
Steps communicate via `ProvisionContext`. Each returns `StepResult(status, detail)` with `ok`/`changed`/`skipped`/`failed`. Every step is independently testable with a mocked `ServerConnection`.

### 5. Shell injection defense — security-critical
ALL values in `conn.run()` strings MUST use `shlex.quote()`. No exceptions. Especially critical with `needs_sudo` root escalation.

### 6. Server resolution cascade — predictable priority
All commands use `resolve_server()` from `commands/resolve.py`. Priority: explicit IP > named server > local mode > single server auto-select > prompt > fail.

### 7. API quirk testing — regression prevention
When wrapping an external API with quirks, write tests that verify the quirk is handled. Name the test after the quirk. Exemplified by `test_panel.py`.

### 8. Fail-with-context — user-friendly errors
Every `fail()` includes `hint_type` (`"user"`, `"system"`, `"bug"`) and action items. Suggest next troubleshooting tool: `meridian test` → `meridian preflight` → `meridian doctor` → GitHub issues.

### 9. Idempotent provisioning — safe re-runs
Every step checks existing state before acting. Re-running `meridian deploy IP` is always safe. Steps return `ok` or `changed`, never duplicate work.

### 10. Single source of truth for each concern
Every piece of information has exactly one canonical source. Downstream consumers derive, never duplicate. Examples: `VERSION` (version), `INBOUND_TYPES` (protocol types), `CLAUDE.md` (architecture). The XHTTP-behind-Caddy architecture follows this pattern: XHTTP uses the same Caddy reverse-proxy pattern as WSS rather than inventing a separate external-port mechanism.

## Backlog & tech debt

See `BACKLOG.md` for the full prioritized task list with completion status.

## GitHub community files

- `.github/ISSUE_TEMPLATE/bug_report.yml` — structured bug report with doctor prompt
- `.github/ISSUE_TEMPLATE/connection_issue.yml` — connection troubleshooting with --preflight prompt
- `.github/ISSUE_TEMPLATE/feature_request.yml` — feature requests by area
- `.github/ISSUE_TEMPLATE/config.yml` — disables blank issues, links to docs
- `SECURITY.md` — vulnerability reporting policy and security design overview
- `CONTRIBUTING.md` — development setup, PR guidelines, testing approach
