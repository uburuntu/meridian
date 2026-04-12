# tests

```bash
make test                              # pytest only (~700 tests, ~17s)
make system-lab                        # multi-node Docker lab (TODO: rewrite for Remnawave)
uv run pytest tests/ -v --tb=short     # verbose
uv run pytest tests/ -k "test_name"    # by pattern
```

## Test layers

| Layer | What | Where | Speed |
|-------|------|-------|-------|
| **Unit** | MockConnection-based provisioner steps, config parsing, cluster/credential handling | `tests/` (pytest) | ~17s |
| **Integration** | TODO: Remnawave Docker container, panel API (3x-ui integration removed in v4) | — | — |
| **E2E** | TODO: Rewrite for Remnawave (currently references 3x-ui containers) | `tests/e2e/` | — |
| **System lab** | TODO: Rewrite for Remnawave (currently references 3x-ui containers) | `tests/systemlab/` | — |

## Testing philosophy

**Integration-level verification** — tests ensure contracts hold (API returns X → we handle Y), not that every function has a unit test.

**MockConnection pattern** — `conn.when("pattern", stdout=..., rc=0)` stubs SSH commands by substring match. First match wins.

## Fixture organization

Top-level `conftest.py` provides:
- **`tmp_home`** — isolates `~/.meridian/` per test via env var + monkeypatch. Both env AND config module constants must be patched.
- **`sample_proxy_yml`** / **`sample_v1_proxy_yml`** — legacy credential fixtures (kept for migration/credential tests).
- **`servers_file`** / **`creds_dir`** — pre-built directory structures.

## Conventions

- **Quirk-named tests** — e.g., `test_login_uses_form_urlencoded_not_json()`. The test name IS the documentation.
- **RFC 5737 IPs** — always `198.51.100.x` for test data, never real IPs.
- **Idempotency dual-path** — provisioner tests verify both "needs change" and "already done" paths.

## Pitfalls

- **Module-level mutable state** — globals like `_warned_servers` can leak between tests. Clear in fixtures.
- **`tmp_home` must patch both** — env var AND `meridian.config` attributes.
- **MockConnection substring matching** — `when("grep", rc=1)` matches ANY command containing "grep". Use specific patterns.
