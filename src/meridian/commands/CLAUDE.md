# commands — One module per subcommand

## Design decisions

**One file per command** — keeps concerns isolated. Each is a Typer sub-app registered in `cli.py`.

**Server resolution cascade** in `resolve.py` — strict priority order ensures predictable behavior:
1. Explicit IP → 2. `--server` name → 3. `local` keyword → 4. Single-server auto-select → 5. Multi-server prompt → 6. Fail with hint

**Three-step pattern**: resolve → ensure connection → fetch credentials. Every server-touching command follows this. Deviating causes subtle bugs.

**Version mismatch check** — `fetch_credentials()` compares `deployed_with` against running CLI. Warns once per server per session. Non-blocking.

**CLI UX vision** — every command output is a guided experience, not a status dump:
- **Educate** — explain *why*, not just what. A user who runs `deploy` should understand Reality camouflage without reading docs. Help text teaches; it doesn't just label flags.
- **Unbreak paths** — every error and broken state must suggest the recovery protocol. Deployment failed? → `meridian preflight`. Server unreachable? → `meridian test`. Weird state? → `meridian teardown` + `meridian deploy`.
- **Upsell the next step** — after `deploy`, suggest `test` and `client add`. After `client add`, suggest `client list` and `test`. Every command's output should make the user aware of what's possible next. The CLI is a guided tour, not a dead end.
- **Cohesive flag language** — same flag means the same thing everywhere. No `--name` meaning three different things on three commands.

**Wizard UX conventions** — the deploy wizard uses `console.py` helpers exclusively:
- **`choose()`** for any decision with 2+ options. Never raw Y/n prompts. Shows numbered list, user picks a number. Default is always 1.
- **`prompt()`** for free-text input (IP address, domain, server name). Show defaults in brackets.
- **`confirm()`** only for the final deploy confirmation. One per command, at the end.
- **Section pattern**: bold header → dim description → blank line → `choose()`/`prompt()`.
- **`rich.status.Status`** spinner for any operation >5 seconds (scan, download). Same style as provisioner steps.
- **Summary Panel** before deploy: show all chosen settings so user can review before confirming.

## What's done well

- **`local` keyword everywhere** — `deploy local`, `check local`, `--server local` all work. Case-insensitive. Same code path.

## Pitfalls

- **Local mode has two entry points** — `local` keyword and root auto-detect. They converge on `local_mode=True` but differ on `creds_dir`.
- **Write commands must fail closed on refresh/sync** — if a command mutates credentials, a stale local cache cannot be trusted and a failed post-save sync must abort before success output or handoff artifact generation.
- **`console.fail()` always exits** — raises `typer.Exit(1)`. Only call from command entry points, never library code.
- **`dev` subcommand is hidden** — not shown in `--help`. Intentional — developer tools only.
