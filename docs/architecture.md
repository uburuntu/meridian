# Architecture

Meridian is a CLI tool that deploys censorship-resistant VLESS+Reality proxy servers. It connects to a VPS via SSH, runs Ansible playbooks to configure Docker/Xray/HAProxy/Caddy, and manages clients through the 3x-ui panel API. Designed for semi-technical users who share VPN access with less technical people.

## Component overview

```
User's laptop                     VPS Server (Debian/Ubuntu)
┌──────────────────┐              ┌─────────────────────────┐
│ meridian CLI     │──── SSH ────>│ Docker: 3x-ui + Xray    │
│ (Python/Typer)   │              │                         │
│                  │── API ──────>│ HAProxy :443 (SNI route) │
│ Ansible playbooks│              │ Caddy (auto-TLS)        │
│ (bundled in pkg) │              │                         │
│                  │              │ Credentials:            │
│ ~/.meridian/     │<── sync ────│ /etc/meridian/           │
│  credentials/    │              └─────────────────────────┘
│  servers         │
└──────────────────┘
```

## Key files to read first

| File | Purpose |
|------|---------|
| `src/meridian/cli.py` | Entry point, all subcommands registered here |
| `src/meridian/commands/setup.py` | Interactive wizard + playbook execution |
| `src/meridian/credentials.py` | `ServerCredentials` dataclass (YAML load/save) |
| `src/meridian/ssh.py` | SSH connection, local mode detection, `tcp_connect` |
| `src/meridian/ansible.py` | Playbook runner, inventory generation, Ansible bootstrap |
| `src/meridian/playbooks/playbook.yml` | Main deployment playbook |
| `src/meridian/playbooks/roles/xray/tasks/configure_panel.yml` | 3x-ui API interactions |
| `src/meridian/playbooks/group_vars/all.yml` | Default variables (SNI, ports, versions) |
| `src/meridian/playbooks/roles/output/templates/connection-info.html.j2` | Client-facing HTML page |
| `tests/test_cli.py` | CLI smoke tests (good for understanding available commands) |

## What happens during `meridian setup`

1. CLI resolves server IP (argument, saved server, or interactive prompt)
2. CLI checks SSH connectivity, detects if running on the server itself
3. Interactive wizard prompts for domain, SNI, XHTTP (unless `--yes`)
4. CLI bootstraps Ansible if not installed (pipx -> pip3 -> apt cascade)
5. CLI generates `~/.meridian/inventory.yml` and runs `playbook.yml`
6. Playbook installs Docker, deploys 3x-ui container, generates x25519 keys
7. Playbook configures VLESS+Reality inbound via 3x-ui REST API
8. If domain: adds HAProxy (SNI routing), Caddy (TLS), VLESS+WSS (CDN fallback)
9. Hardens server: UFW firewall, SSH key-only, BBR congestion control
10. Outputs QR codes + saves HTML connection page with client links
11. Syncs credentials to `/etc/meridian/` on the server (source of truth)

## Credential lifecycle

- **Server** (`/etc/meridian/proxy.yml`) is the source of truth
- **Local** (`~/.meridian/credentials/<IP>/proxy.yml`) is a cache
- Playbook post_tasks sync local -> server after every run
- CLI fetches from server via SSH when local cache is missing
- `meridian server add IP` pulls credentials from server to local cache
- `meridian uninstall` deletes both server and local copies

## Critical gotchas

These are the top things that will break if you are not careful:

1. **`body_format: json` for API calls.** The 3x-ui inbound/client API MUST use `body_format: json`, not `form-urlencoded`. Ansible's uri module silently corrupts inline JSON in form-urlencoded bodies. The API returns `success: true` but stores garbage.

2. **`jinja2_native = True` in ansible.cfg.** Required so `body_format: json` sends native integers (e.g., port numbers). Removing it breaks API calls with type errors. Safe with mixed text+expression templates because Jinja2 NativeEnvironment only returns native types for single-expression templates.

3. **Handler flush before port checks.** `roles/output/tasks/main.yml` calls `meta: flush_handlers` before verifying ports. Without this, HAProxy/Caddy restart handlers have not fired yet and port 443 appears down.

4. **Connection info template sync.** There are multiple `connection-info.html.j2` templates (output role, caddy role). CSS, JS, and app download links must stay identical across all copies.

5. **Client email naming convention.** Clients map to 3x-ui emails as `reality-{name}`, `wss-{name}`, `xhttp-{name}`. The first client uses `reality-default`. Deleting clients requires the UUID, not the email (email-based deletion silently succeeds without actually deleting).

## Testing

```bash
make ci            # Full local CI: lint + format + test + ansible-lint + syntax-check + templates
make test          # pytest only (credentials, servers, CLI, ansible, update logic)
make lint          # ruff check + ruff format --check
make ansible-lint  # Ansible linting
make templates     # Jinja2 template rendering with mock variables
```

CI cannot test actual deployments. For that, use a real VPS and run the full uninstall -> install cycle. Integration tests (`test_integration_3xui.py`) require a running 3x-ui Docker container and are auto-skipped when the container is not available.
