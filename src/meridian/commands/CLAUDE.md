# commands — One module per subcommand

## Design decisions

**One file per command** — keeps concerns isolated. Each is a Typer sub-app registered in `cli.py`.

**Cluster-first pattern** — commands load `ClusterConfig` from `cluster.yml`, create `MeridianPanel` client, call REST API. No SSH needed for client/fleet operations.

**Server resolution cascade** in `resolve.py` — strict priority order for server-touching commands (deploy, node add):
1. Explicit IP → 2. `--server` name → 3. `local` keyword → 4. Single-server auto-select → 5. Multi-server prompt → 6. Fail with hint

**Command groups**: `client` (add/show/list/remove), `node` (add/list/remove), `relay` (deploy/list/remove/check), `fleet` (status/recover). Top-level: `deploy`, `migrate`, `test`, `probe`, `doctor`, `teardown`.

## What's done well

- **`client add` is one API call** — `panel.create_user(name)`. No multi-step credential sync.
- **`fleet recover`** — reconstruct cluster.yml from panel API when local state is lost.

## Pitfalls

- **`console.fail()` always exits** — raises `typer.Exit` with semantic codes (user=2, system=3, bug=1). Only call from command entry points.
- **`confirm()` returns bool** — returns True on accept, False on reject. Callers must check `if not confirm(...): raise typer.Exit(1)`.
- **Panel node cannot be removed** — `node remove` blocks removal of the panel host server.
