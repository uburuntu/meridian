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
inventory.yml              Standalone inventory
inventory-chain.yml.example Chain inventory template
group_vars/all.yml         Shared defaults (version pin, ports, limits)
group_vars/exit.yml        Exit node defaults (chain)
group_vars/relay.yml       Relay node defaults (chain)
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

## Key API patterns

- 3x-ui login: `POST /login` (form-urlencoded) returns session cookie
- Add inbound: `POST /panel/api/inbounds/add` (form-urlencoded with JSON in `settings`, `streamSettings`, `sniffing` fields)
- List inbounds: `GET /panel/api/inbounds/list` (check by remark before creating)
- Update settings: `POST /panel/setting/update` (JSON body)
- Update credentials: `POST /panel/setting/updateUser` (JSON body)
- Read settings: `POST /panel/setting/all`
- Xray template config: set `xrayTemplateConfig` field in `/panel/setting/update`
- Key generation: `docker exec 3x-ui /app/bin/xray-linux-amd64 x25519` (parse Private/Public key lines), `docker exec 3x-ui /app/bin/xray-linux-amd64 uuid`

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
