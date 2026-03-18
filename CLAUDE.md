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
- Credentials are persisted locally in `credentials/<host>.yml` for idempotent re-runs. Credentials are saved BEFORE changing the panel password to prevent lockout on failure.
- Docker installation is skipped if Docker is already running with containers.
- In no-domain mode, the panel binds to localhost only (SSH tunnel required).
- 3x-ui Docker image is pinned to a tested version (`threexui_version` in group_vars) to prevent API breakage.
- All tasks handling secrets use `no_log: true` to keep credentials out of terminal output.

## Project structure

```
playbook.yml              Standalone mode
playbook-chain.yml         Chain mode (exit first, then relay)
playbook-uninstall.yml     Clean removal of proxy components
inventory.yml              Standalone inventory
inventory-chain.yml.example Chain inventory template
group_vars/all.yml         Shared defaults (version pin, ports, limits)
group_vars/exit.yml        Exit node defaults (chain)
group_vars/relay.yml       Relay node defaults (chain)
setup.sh                   One-command installer (interactive wizard + flag mode)
docs/index.html            Website hosted on meridian.msu.rocks (GitHub Pages)
docs/CNAME                 Custom domain for GitHub Pages
tests/render_templates.py  CI template rendering test
.github/workflows/ci.yml   CI pipeline (lint, syntax, templates, links)
.ansible-lint              Ansible lint configuration
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
- `setup.sh` downloads from `github.com/uburuntu/meridian/archive/refs/heads/main.tar.gz` — repo name/org hardcoded
- `setup.sh` restores credentials from `~/meridian/`, `~/vpn-credentials/`, or orphaned `/tmp/*/credentials/` dirs

### docs/index.html ↔ setup.sh
- Website command builder generates `curl ... setup.sh | bash -s -- IP` commands — flag names (`--domain`, `--user`, `--uninstall`) must match `setup.sh`
- The raw GitHub URL in the website must match the actual repo path
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
- **Always use context7 MCP to check up-to-date docs** before writing Ansible tasks, Docker configs, or Caddy configs — stale patterns cause real deployment failures
- **curl|bash stdin trap**: in `setup.sh`, any command that reads stdin (ssh, curl, wget, pip3) MUST have `</dev/null` — otherwise it consumes the rest of the piped script and bash silently exits
- **Ansible debug vs shell for terminal output**: use `shell` with `printf`/`cat` for output containing ANSI codes (QR codes); `debug msg:` JSON-escapes them
- **pip3 install on modern Debian/Ubuntu**: must handle PEP 668 "externally managed environment" — try pipx, then `--user`, then `--break-system-packages`, then apt
- **Decoy site default title**: must NOT contain "Meridian" — would link the decoy site back to this GitHub repo. Currently "Westbridge Partners", randomized per deployment via hostname hash
- **setup.sh interactive prompts**: use `read -r VAR < /dev/tty` (not stdin) so it works in `curl | bash`; detect public IPv4 with `curl -4` to avoid IPv6; suggest domain from Caddy config or saved credentials

## Known issues / tech debt

- `configure_panel.yml` is ~90% duplicated between `xray` and `xray_relay` roles (the 35-field settings payload is copy-pasted). Should extract to a shared task file.
- Three connection-info HTML templates drift independently. Should use a single template with conditional blocks.
- Pre-tasks (IP resolution, credential loading, qrencode check) are duplicated across playbook.yml and playbook-chain.yml.
- No key/credential rotation mechanism. Re-deploy with deleted credentials file is the only option.
- No post-deployment monitoring or health checks (cron/watchdog).
- 3x-ui database at `/opt/3x-ui/db/` grows without bound (traffic stats).
