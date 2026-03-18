# Contributing to Meridian

Thanks for your interest! Here's how to help.

## Reporting Issues

- **Bug?** Use the [bug report template](https://github.com/uburuntu/meridian/issues/new?template=bug_report.yml) — run `--rage` first to collect diagnostics
- **Connection not working?** Use the [connection issue template](https://github.com/uburuntu/meridian/issues/new?template=connection_issue.yml) — run `--check` first
- **Feature idea?** Use the [feature request template](https://github.com/uburuntu/meridian/issues/new?template=feature_request.yml)
- **Security vulnerability?** See [SECURITY.md](SECURITY.md) — do NOT open a public issue

## Development Setup

```bash
git clone https://github.com/uburuntu/meridian.git && cd meridian
pip install ansible
ansible-galaxy collection install -r requirements.yml

# Run linter
pip install ansible-lint
ansible-lint

# Run template tests
pip install jinja2
python3 tests/render_templates.py

# Check setup.sh syntax
bash -n setup.sh
```

## Pull Requests

1. Fork the repo and create a branch from `main`
2. Make your changes — keep them focused and minimal
3. Ensure CI passes (lint, syntax check, template rendering)
4. Test on a real server if possible — CI can't catch deployment issues
5. Open a PR with a clear description of what and why

## Architecture Notes

See [CLAUDE.md](CLAUDE.md) for detailed architecture, implicit dependencies, and conventions. Key points:

- **All tasks use FQCNs** (`ansible.builtin.uri`, not `uri`)
- **Secrets use `no_log: true`** — never expose credentials in output
- **setup.sh stdin trap** — commands that read stdin need `</dev/null` in curl|bash mode
- **Three connection-info templates** must stay in sync (output, decoy_site, output_relay)
- **Caddy config** goes in `/etc/caddy/conf.d/meridian.caddy`, not the main Caddyfile

## Testing

There's no way to fully test without a real server. The CI pipeline validates:
- Ansible lint and syntax
- Jinja2 template rendering with mock variables
- Shell script syntax
- Ansible dry-run (`--check`) with local connection

For deployment testing, use a cheap VPS and run the full uninstall → install cycle.
