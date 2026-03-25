# commands — One module per subcommand

Each file (setup, client, server, relay, check, scan, ping, diagnostics, uninstall, dev) is a Typer sub-app registered in `cli.py`.

## Server resolution cascade

Shared logic in `resolve.py`. Resolution order:

1. Explicit IP argument
2. Named server (`--server name` lookup in credentials)
3. Local keyword (`local`/`locally` → detect public IP, use `bash -c`)
4. Auto-select (single server in credentials → use it)
5. Interactive prompt (multiple servers → ask user)
6. Fail with context

## Key patterns

- **`fetch_credentials()`** — loads from local cache or fetches via SSH. Checks version mismatch between local CLI and remote server, warns if incompatible
- **`resolve.py`** — `is_local_keyword()`, `detect_public_ip()`, `resolve_server()` used across all commands
- **`console.fail()`** — always include `hint_type` and actionable suggestions. Raises `typer.Exit(1)`
- **`dev` subcommand** — hidden from `--help`, developer/debugging tools only

## Adding a new subcommand

1. Create `commands/mycommand.py` with a Typer app
2. Register in `cli.py`
3. Add tests
4. Update README.md, website docs, CLAUDE.md
