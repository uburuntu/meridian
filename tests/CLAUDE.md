# tests

## Quick reference

```bash
make test                              # pytest only
uv run pytest tests/ -v --tb=short     # verbose with short tracebacks
uv run pytest tests/test_foo.py -v     # single file
uv run pytest tests/ -k "test_name"    # by name pattern
```

## Current state

493 pass, 6 skip as of 2026-03-25.

## Conventions

- **API quirk testing** — tests verify the quirk is handled, named after the quirk (e.g., `test_login_uses_form_urlencoded_not_json`)
- **Fixtures** in `conftest.py` — shared mocks for `ServerConnection`, `ProvisionContext`, credentials
- **Demo data** — use RFC 5737 IPs (`198.51.100.x`), never real server IPs
- **Shell injection** — tests should verify `shlex.quote()` on any `conn.run()` interpolated values
- **Idempotent steps** — provisioner step tests should verify state-check-before-act behavior
