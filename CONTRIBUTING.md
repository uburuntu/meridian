# Contributing to Meridian

Thanks for your interest! Here's how to help.

## Reporting Issues

- **Bug?** Use the [bug report template](https://github.com/uburuntu/meridian/issues/new?template=bug_report.yml) — run `meridian diagnostics` first to collect info
- **Connection not working?** Use the [connection issue template](https://github.com/uburuntu/meridian/issues/new?template=connection_issue.yml) — run `meridian ping` and `meridian check` first
- **Feature idea?** Use the [feature request template](https://github.com/uburuntu/meridian/issues/new?template=feature_request.yml)
- **Security vulnerability?** See [SECURITY.md](SECURITY.md) — do NOT open a public issue

## Development Setup

```bash
git clone https://github.com/uburuntu/meridian.git && cd meridian

# Install the CLI in editable mode with dev dependencies
pip install -e ".[dev]"

# Install Ansible (for playbook validation)
pip install ansible
ansible-galaxy collection install -r requirements.yml

# Run tests
pytest tests/ -v

# Run linter
ruff check src/ tests/
ruff format --check src/ tests/

# Run Ansible lint
pip install ansible-lint
ansible-lint

# Run template rendering test
python3 tests/render_templates.py
```

## Project Structure

The CLI is a Python package (`src/meridian/`) distributed via PyPI as `meridian-vpn`. Ansible playbooks are bundled inside the package as `src/meridian/playbooks/`.

Key modules:
- `cli.py` — Typer app, subcommand registration
- `commands/` — One module per subcommand (setup, client, check, etc.)
- `credentials.py` — `ServerCredentials` dataclass for YAML credential management
- `servers.py` — `ServerRegistry` for the known servers index
- `ansible.py` — Playbook execution via subprocess

## Pull Requests

1. Fork the repo and create a branch from `main`
2. Make your changes — keep them focused and minimal
3. Ensure CI passes: `pytest`, `ruff check`, `ruff format --check`, `ansible-lint`
4. Test on a real server if possible — CI can't catch deployment issues
5. Open a PR with a clear description of what and why

## Architecture Notes

See [CLAUDE.md](CLAUDE.md) for detailed architecture, implicit dependencies, and conventions. Key points:

- **All Ansible tasks use FQCNs** (`ansible.builtin.uri`, not `uri`)
- **Secrets use `no_log: true`** — never expose credentials in output
- **Three connection-info templates must stay in sync** (output/caddy/output_relay)
- **Caddy config** goes in `/etc/caddy/conf.d/meridian.caddy`, not the main Caddyfile
- **Playbook sync** — when editing playbooks at repo root, copy changes to `src/meridian/playbooks/`

## Testing

There's no way to fully test without a real server. The CI pipeline validates:
- Python tests (`pytest`) — credentials, servers, CLI, ansible, update logic
- Python lint (`ruff`) — style and import checks
- Ansible lint and syntax
- Jinja2 template rendering with mock variables
- Shell script syntax (`install.sh`, `setup.sh`)
- Ansible dry-run (`--check`) with local connection

For deployment testing, use a cheap VPS and run the full uninstall → install cycle.
