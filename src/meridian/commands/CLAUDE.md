# commands — One module per subcommand

## Design decisions

**One file per command** — keeps concerns isolated. Each is a Typer sub-app registered in `cli.py`.

**Server resolution cascade** in `resolve.py` — strict priority order ensures predictable behavior:
1. Explicit IP → 2. `--server` name → 3. `local` keyword → 4. Single-server auto-select → 5. Multi-server prompt → 6. Fail with hint

**Three-step pattern**: resolve → ensure connection → fetch credentials. Every server-touching command follows this. Deviating causes subtle bugs.

**Version mismatch check** — `fetch_credentials()` compares `deployed_with` against running CLI. Warns once per server per session. Non-blocking.

## What's done well

- **`local` keyword everywhere** — `deploy local`, `check local`, `--server local` all work. Case-insensitive. Same code path.
- **Credential sync** — modify locally first, SCP back to server. No lockout on network failure.

## Pitfalls

- **Local mode has two entry points** — `local` keyword and root auto-detect. They converge on `local_mode=True` but differ on `creds_dir`.
- **SCP sync is fire-and-forget** — if SCP fails, server and local creds diverge silently.
- **`console.fail()` always exits** — raises `typer.Exit(1)`. Only call from command entry points, never library code.
- **`dev` subcommand is hidden** — not shown in `--help`. Intentional — developer tools only.
