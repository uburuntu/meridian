# CLAUDE.md

## Project overview

Ansible automation for deploying censorship-resistant VLESS+Reality proxy servers. Supports standalone single-server mode and a two-server relay chain for IP whitelist bypass.

## Architecture

- **Standalone mode** (`playbook.yml`): Single server with VLESS+Reality. Optional domain mode adds HAProxy (SNI routing), Caddy (TLS + decoy site), and VLESS+WSS (CDN fallback via Cloudflare).
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
playbook.yml              Standalone mode
playbook-chain.yml         Chain mode (exit first, then relay)
playbook-uninstall.yml     Clean removal of proxy components + credentials
inventory.yml              Standalone inventory
inventory-chain.yml.example Chain inventory template
group_vars/all.yml         Shared defaults (version pin, ports, limits)
group_vars/exit.yml        Exit node defaults (chain)
group_vars/relay.yml       Relay node defaults (chain)
setup.sh                   One-command installer (interactive wizard + flag mode)
docs/index.html            Website hosted on meridian.msu.rocks (GitHub Pages)
docs/setup.sh              Copy of setup.sh served by GitHub Pages (synced by CD)
docs/CNAME                 Custom domain for GitHub Pages
pre_tasks/                 Shared pre-task files (resolve_ip, check_qrencode, load_credentials)
tests/render_templates.py  CI template rendering test (with Ansible filter mocks)
.github/workflows/ci.yml   CI pipeline (lint, syntax, templates, shell, dry-run)
.github/workflows/cd.yml   CD pipeline (sync setup.sh → docs/setup.sh)
.ansible-lint              Ansible lint configuration
SECURITY.md                Vulnerability reporting policy
CONTRIBUTING.md            Development setup and PR guidelines
roles/
  common/                  OS packages, SSH hardening, UFW, BBR
  docker/                  Docker CE installation (idempotent)
  xray/                    3x-ui deploy + VLESS inbound config via API
  xray_relay/              Relay node: user inbound + exit outbound + routing
                           (reuses xray/templates/docker-compose.yml.j2)
  haproxy/                 TCP SNI router (domain mode)
  caddy/                   Reverse proxy + auto-TLS (domain mode)
  decoy_site/              Static decoy website + connection info page
  output/                  Terminal display + local file generation + port verification
  output_relay/            Relay-specific output
```

## Implicit dependencies & cross-file relationships

These are easy to break by editing one file without updating the others:

### setup.sh ↔ playbooks
- `setup.sh` passes `-e server_public_ip=$SERVER_IP -e credentials_dir=$HOME/meridian` to `ansible-playbook`
- All output templates use `{{ server_public_ip }}` instead of `{{ ansible_host }}` for user-facing URLs
- `setup.sh` writes `inventory.yml` with the user-provided IP/user; adds `ansible_connection: local` when running on the target server itself
- `setup.sh` adds `ansible_become: true` for non-root users
- `setup.sh --uninstall` runs `playbook-uninstall.yml`
- `setup.sh` is served from `https://meridian.msu.rocks/setup.sh` (GitHub Pages) — synced from repo root by CD workflow
- `setup.sh` downloads the playbook tarball from `github.com/uburuntu/meridian/archive/refs/heads/main.tar.gz`
- `setup.sh` restores credentials from `~/meridian/` locally, or fetches from server via SSH if not found

### setup.sh flags
- `--domain DOMAIN` — add decoy website + CDN fallback
- `--sni HOST` — Reality camouflage target (default: www.microsoft.com), passed as `-e reality_sni=`
- `--user USER` — SSH user (default: root)
- `--uninstall` — remove proxy from server, deletes credentials
- `--check` / `--preflight` — pre-flight validation without installing (SNI, ports, DNS, OS, disk)
- `--rage` / `--diagnostics` — collect system diagnostics for bug reports, auto-redacts secrets
- `--yes` / `-y` — skip confirmation prompts (for non-interactive/CI use)

### docs/index.html ↔ setup.sh
- Website command builder has tabbed interface (Install/Pre-flight/Diagnostics/Uninstall) — flag names must match `setup.sh`
- setup.sh is served from `meridian.msu.rocks/setup.sh` — the `docs/setup.sh` copy is synced by CD workflow (`.github/workflows/cd.yml`)
- Website references the same app download links as the HTML templates in roles

### Connection info HTML templates (3 copies)
- `roles/decoy_site/templates/connection-info.html.j2` — served on the server (domain mode)
- `roles/output/templates/connection-info.html.j2` — saved locally (standalone/exit)
- `roles/output_relay/templates/connection-info.html.j2` — saved locally (relay)
- All three have similar CSS/JS but different Jinja2 variables; app download links must be kept in sync across all three

### Credential flow
- `setup.sh` overrides `credentials_dir` to `$HOME/meridian/` so credentials survive temp dir cleanup
- `roles/xray/tasks/configure_panel.yml` saves to `{{ credentials_file }}` which is `{{ credentials_dir }}/{{ inventory_hostname }}.yml`
- `playbook.yml` and `playbook-chain.yml` load from the same file in pre_tasks via `include_vars`
- `playbook-chain.yml` relay play loads EXIT node credentials from `{{ credentials_dir }}/{{ exit_node }}.yml`
- Domain is saved to credentials file for detection on re-runs
- `setup.sh` uninstall reads saved credentials to find the server IP
- `playbook-uninstall.yml` deletes credentials from both server (`~/meridian/`) and locally
- `setup.sh` fetches credentials from server via SSH when not found locally (handles cross-machine runs)

### Caddy config pattern
- Meridian writes to `/etc/caddy/conf.d/meridian.caddy` (not the main Caddyfile)
- Main Caddyfile gets a single `import /etc/caddy/conf.d/*.caddy` line added via `lineinfile`
- Uninstall removes only `/etc/caddy/conf.d/meridian.caddy`, not the user's Caddyfile
- `setup.sh` domain detection checks both `conf.d/meridian.caddy` and `Caddyfile` for the domain

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
- `fail()` in setup.sh suggests `--rage` and links to GitHub issues
- Success output mentions feedback URL
- Ansible connection summary includes feedback section
- Website has troubleshooting with `--check` and `--rage` commands
- README has troubleshooting section

## Key API patterns

- 3x-ui login: `POST /login` (form-urlencoded) returns session cookie
- Add inbound: `POST /panel/api/inbounds/add` (form-urlencoded with JSON in `settings`, `streamSettings`, `sniffing` fields)
- List inbounds: `GET /panel/api/inbounds/list` (check by remark before creating)
- Update settings: `POST /panel/setting/update` (JSON body)
- Update credentials: `POST /panel/setting/updateUser` (JSON body)
- Read settings: `POST /panel/setting/all`
- Xray template config: set `xrayTemplateConfig` field in `/panel/setting/update`
- Key generation: `docker exec 3x-ui sh -c '/app/bin/xray-linux-* x25519'` (parse PrivateKey/Password lines), `docker exec 3x-ui sh -c '/app/bin/xray-linux-* uuid'`

## Build and test

```bash
# Install dependencies
pip install ansible
ansible-galaxy collection install -r requirements.yml

# Validate YAML syntax
python3 -c "import yaml, glob; [yaml.safe_load(open(f)) for f in glob.glob('**/*.yml', recursive=True)]"

# Run template rendering test
pip install jinja2 && python3 tests/render_templates.py

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
- **Always use context7 MCP to check up-to-date docs** before writing Ansible tasks, Docker configs, or Caddy configs — stale patterns cause real deployment failures
- **curl|bash stdin trap**: in `setup.sh`, any command that reads stdin (ssh, curl, wget, pip3) MUST have `</dev/null` — otherwise it consumes the rest of the piped script and bash silently exits
- **Ansible debug vs shell for terminal output**: use `shell` with `printf`/`cat` for output containing ANSI codes (QR codes); `debug msg:` JSON-escapes them
- **pip3 install on modern Debian/Ubuntu**: must handle PEP 668 "externally managed environment" — try pipx, then `--user`, then `--break-system-packages`, then apt
- **pip user bin PATH**: after pip3 install --user, add `~/.local/bin` (Linux) and `~/Library/Python/*/bin` (macOS) to PATH
- **Decoy site default title**: must NOT contain "Meridian" — would link the decoy site back to this GitHub repo. Currently "Westbridge Partners", randomized per deployment via hostname hash
- **setup.sh interactive prompts**: use `read -r VAR < /dev/tty` (not stdin) so it works in `curl | bash`; detect public IPv4 with `curl -4` to avoid IPv6; suggest domain from Caddy config or saved credentials
- **setup.sh info() function**: uses `printf "%s"` which prints arguments literally — do NOT embed escape codes like `${B}` in arguments passed to `info()`
- **GitHub raw CDN caching**: raw.githubusercontent.com caches for ~60-120s; can't bust with query params or headers, just wait. Serving from meridian.msu.rocks avoids this.
- **HAProxy health checks**: do NOT use `check` on TLS backends (Caddy, Xray) — TCP probes fail on TLS-only ports, causing "backend has no server available" errors. These are local systemd services, not load-balanced pools.
- **setup.sh docs/ sync**: `docs/setup.sh` must stay in sync with root `setup.sh`. The CD workflow auto-syncs on push, but manual edits to docs/setup.sh will be overwritten.

## CI/CD pipelines

### CI (`.github/workflows/ci.yml`) — runs on push and PR
- **Lint**: `ansible/ansible-lint@main` — catches FQCN, YAML style, deprecated patterns
- **Validate**: syntax check all playbooks + template rendering test with Ansible filter mocks
- **Shell**: `bash -n` syntax check + shellcheck + `--help` flag test
- **Dry run**: `ansible-playbook --check` with local connection (validates task structure)
- Skipped lint rules: `var-naming[no-role-prefix]` (would require renaming 90+ variables), `command-instead-of-module` (curl/dig used intentionally)

### CD (`.github/workflows/cd.yml`) — runs on push to main when setup.sh changes
- Copies `setup.sh` → `docs/setup.sh` and auto-commits with `[skip ci]`
- Ensures `meridian.msu.rocks/setup.sh` always serves the latest version

## Known issues / tech debt

- Three connection-info HTML templates share the same design but different Jinja2 variables. CSS/JS is duplicated across all three. A single template with conditional blocks would reduce drift risk.
- No key/credential rotation mechanism. To rotate: uninstall (deletes credentials) then reinstall.
- No post-deployment monitoring beyond cron-based cleanup. No watchdog or alerting.

### Recently addressed
- Panel settings payload extracted to `roles/xray/tasks/apply_panel_settings.yml` — shared by both `xray` and `xray_relay` roles.
- Pre-tasks extracted to `pre_tasks/` directory — `resolve_ip.yml`, `check_qrencode.yml`, `load_credentials.yml` shared by both playbooks.
- Database and log growth: weekly cron jobs vacuum the 3x-ui database (deletes traffic stats older than 30 days) and truncate Docker container logs.

## GitHub community files

- `.github/ISSUE_TEMPLATE/bug_report.yml` — structured bug report with --rage prompt
- `.github/ISSUE_TEMPLATE/connection_issue.yml` — connection troubleshooting with --check prompt
- `.github/ISSUE_TEMPLATE/feature_request.yml` — feature requests by area
- `.github/ISSUE_TEMPLATE/config.yml` — disables blank issues, links to docs
- `SECURITY.md` — vulnerability reporting policy and security design overview
- `CONTRIBUTING.md` — development setup, PR guidelines, testing approach
