# tests

```bash
make test                              # pytest only
uv run pytest tests/ -v --tb=short     # verbose
uv run pytest tests/ -k "test_name"    # by pattern
```

## Testing philosophy

**Integration-level verification** — tests ensure contracts hold (API returns X → we handle Y), not that every function has a unit test. The codebase is integration-heavy; mocking away SSH and APIs doesn't verify real behavior.

**MockConnection pattern** — `conn.when("pattern", stdout=..., rc=0)` stubs SSH commands by substring match. First match wins. Exact matching is too brittle for shell commands with quoting and pipes.

## Fixture organization

Top-level `conftest.py` provides:
- **`tmp_home`** — isolates `~/.meridian/` per test via env var + monkeypatch. Both env AND config module constants must be patched (cached imports leak state otherwise).
- **`sample_proxy_yml`** / **`sample_v1_proxy_yml`** — return Paths, not content. Callers read explicitly.
- **`servers_file`** / **`creds_dir`** — pre-built directory structures.

## Conventions

- **Quirk-named tests** — e.g., `test_login_uses_form_urlencoded_not_json()`. The test name IS the documentation.
- **RFC 5737 IPs** — always `198.51.100.x` for test data, never real IPs.
- **Idempotency dual-path** — provisioner tests verify both "needs change" and "already done" paths.
- **`_strip_ansi()`** — strip Rich color codes before asserting on CLI output.

## Pitfalls

- **Module-level mutable state** — globals like `_warned_servers`, `_qrencode_warned` can leak between tests. Clear in fixtures.
- **`tmp_home` must patch both** — env var AND `meridian.config` attributes. Missing either causes tests to touch real home directory.
- **MockConnection substring matching** — `when("grep", rc=1)` matches ANY command containing "grep". If a `conn.run()` call combines multiple commands (e.g., `grep ... && sed ... || printf ...`), the mock matches the whole string on the first keyword. Keep each `conn.run()` to a single command, or use a more specific pattern in the mock.
