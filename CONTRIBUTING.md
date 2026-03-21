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

# Install the CLI in editable mode with all dev dependencies (uses uv sync --extra dev)
make install

# Run full CI locally (lint + format + test + ansible-lint + syntax-check + templates)
make ci

# Or run individual checks:
make test              # Run Python tests (pytest)
make lint              # Run ruff linter
make format-check      # Check formatting
make ansible-lint      # Run ansible-lint on playbooks
make templates         # Validate Jinja2 template rendering

# Install Ansible collections (if needed for manual playbook runs)
pip install ansible
ansible-galaxy collection install -r src/meridian/playbooks/requirements.yml
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
3. Ensure CI passes: `make ci` (runs all checks locally)
4. Test on a real server if possible — CI can't catch deployment issues
5. Open a PR with a clear description of what and why

## Architecture Notes

See [CLAUDE.md](CLAUDE.md) for detailed architecture, implicit dependencies, and conventions. Key points:

- **All Ansible tasks use FQCNs** (`ansible.builtin.uri`, not `uri`)
- **Secrets use `no_log: true`** — never expose credentials in output
- **Two connection-info templates must stay in sync** (output/caddy)
- **Caddy config** goes in `/etc/caddy/conf.d/meridian.caddy`, not the main Caddyfile


## Testing

There's no way to fully test without a real server. The CI pipeline validates:
- Python tests (`pytest`) — credentials, servers, CLI, ansible, update logic
- Python lint (`ruff`) — style and import checks
- Ansible lint and syntax
- Jinja2 template rendering with mock variables
- Shell script syntax (`install.sh`, `setup.sh`)
- Ansible dry-run (`--check`) with local connection

For deployment testing, use a cheap VPS and run the full uninstall → install cycle.
