# CLAUDE.md

## North-star vision

Meridian exists to make censorship-resistant VPN accessible to everyone. The core idea: a semi-technical person (who can rent a VPS and run commands) becomes the "tech friend" who shares secure VPN access with family, older relatives, and less technical people — via share links, QR codes, and guided connection pages.

**Audience (three tiers):**
1. **Tech friends** — set up a server, share keys with family and friends
2. **Power users** — need fast VPS rebuilds when IPs get blocked regularly
3. **Organizations** — NGOs, journalists, activists helping people in censored regions

**Design principles:**
- **Protocol-agnostic harness** — Meridian doesn't build protocols, it makes the best undetectable ones easy to deploy. Today that's VLESS+Reality; tomorrow it could be something else.
- **Guided wizard** — interactive setup that explains each choice but has smart defaults.
- **Guided handoff** — Meridian's responsibility ends at the server. Client setup is the user's job, but Meridian makes it effortless: polished connection pages with step-by-step instructions, app download links, QR codes, and shareable URLs.
- **Rebuild-fast** — IPs get blocked. Spinning up a fresh VPS and running `meridian deploy` should get you back online in minutes.
- **Aesthetics matter** — every surface is UI/UX. CLI output, terminal colors, QR codes, connection pages, URLs, error messages, docs — all must be clear, beautiful, and feel premium. URLs are UI too: they must be clean, readable, and aesthetically pleasing (no ugly query strings, no random noise in user-facing paths).

## Project overview

Python CLI (`meridian-vpn` on PyPI) for deploying censorship-resistant proxy servers. Supports VLESS+Reality (primary) with XHTTP (enhanced stealth, enabled by default) and optional domain mode for CDN fallback (VLESS+WSS). Relay nodes (Realm TCP forwarder) allow domestic entry points that forward to exit servers abroad. Server provisioning uses a pure-Python provisioner (`src/meridian/provision/`). Website at `getmeridian.org` built with Astro.

## Architecture

- **All modes** deploy HAProxy (port 443, SNI routing) + Caddy (port 80/8443, TLS + web serving). In standalone mode (no domain), Caddy requests a Let's Encrypt IP certificate via ACME `shortlived` profile. In domain mode, Caddy also handles VLESS+WSS (CDN fallback via Cloudflare).
- **XHTTP runs behind Caddy** on 127.0.0.1. Caddy reverse-proxies to it and handles TLS. No extra firewall port needed.
- **HAProxy SNI routing**: port 443, TCP-level SNI inspection without TLS termination, so Reality and Caddy coexist on 443.
- **Caddy config import pattern**: writes to `/etc/caddy/conf.d/meridian.caddy`, main Caddyfile just has `import /etc/caddy/conf.d/*.caddy`.
- **3x-ui managed via REST API** — Docker image pinned to tested version. Panel accessible via HTTPS on a secret Caddy-proxied path.
- **Relay nodes** — lightweight TCP forwarders (Realm, Rust binary) that relay port 443 to an exit server. No Docker, no 3x-ui, no panel. Client → Relay (domestic IP) → Exit (abroad). All protocols work through dumb L4 relay.

## Project structure

```
pyproject.toml             Python package config (hatchling build, PyPI as meridian-vpn)
VERSION                    Version source of truth (read by hatchling + importlib.metadata)
src/meridian/              Python CLI package
  commands/                One module per subcommand
  provision/               Pure-Python step pipeline provisioner
  templates/pwa/           PWA connection page (vanilla JS, no build step)
website/                   Astro static site (getmeridian.org)
  src/components/          Astro UI components
  src/styles/              Design tokens, theming, typography
  src/pages/               File-based routing, machine-readable endpoints
tests/                     pytest tests
  provision/               Provisioner step tests (MockConnection pattern)
  e2e/                     End-to-end deployment in Docker
.github/workflows/         CI (9 jobs) + Release (VERSION-driven)
```

## Per-folder CLAUDE.md convention

Every meaningful folder has its own `CLAUDE.md` capturing **design decisions, what's done well, and pitfalls**. This is a self-sustaining system:

**What goes in a folder CLAUDE.md:**
- WHY decisions were made (not WHAT the code does — that changes)
- What's done really well and the design decision behind it
- Pitfalls: things learned the hard way that future developers must not repeat

**What does NOT go in:**
- Line numbers, function signatures, or anything that drifts as code evolves
- Exhaustive file listings (use `ls`)
- Duplicated info from the root CLAUDE.md

**When to create one:** any folder with 3+ files and distinct architectural concerns. Skip tiny leaf folders.

**When to update one:** after making a design decision, fixing a subtle bug, or discovering a pitfall. The CLAUDE.md is a living document — update it as part of the PR, not as a separate task.

**Self-healing property:** AI assistants read these files automatically. A good CLAUDE.md prevents the same mistake from being made twice, even across different developers and sessions. Each pitfall documented is a bug that never recurs.

## Local development

```bash
make install               # uv sync --extra dev --reinstall-package meridian-vpn
uv run meridian --version  # verify you're running the local code
uv run meridian deploy     # run any command via uv run
```

**Why `uv run`?** It ensures you use the local editable install from the repo, not a system-wide `meridian` (e.g., from `uv tool install` or `pipx`). Always use `uv run meridian` during development.

**Why `--reinstall-package`?** The `VERSION` file is the version source of truth, but `uv sync` caches package metadata. After bumping `VERSION`, run `make install` to refresh.

**Quick reference:**
```bash
make install               # install/refresh local dev build
make ci                    # lint + format + test + templates
make test                  # pytest only
cd website && npm install && npm run build  # Astro + Pagefind
```

## Conventions

### Security
- **Shell injection**: ALL `conn.run()` interpolated values MUST use `shlex.quote()`
- **Referrer policy**: `<meta name="referrer" content="no-referrer">` on all pages
- **Self-hosted fonts**: zero external requests (Google Fonts blocked in target regions)
- **Demo data**: use RFC 5737 IPs (`198.51.100.x`), never real server IPs in public files
- **Credential lockout prevention**: credentials saved BEFORE changing panel password

### Build
- Cross-platform: `base64 | tr -d '\n'` (not `base64 -w0`)
- `curl|bash stdin trap`: commands reading stdin MUST have `</dev/null`
- AI docs generated from human docs (en/). Run `make ai-docs` locally; CI generates automatically
- Pre-push hook: `.githooks/pre-push` runs 11 checks. Install with `make hooks`
- **Always use context7 MCP** before writing code depending on external libraries
- **context-hub MCP**: integrated — provides `/context-hub.md` endpoint for AI-readable project docs
- **Translations**: use Haiku model agents (`model: "haiku"`) for fast i18n translations
- **GitHub CLI**: use `GH_CONFIG_DIR=~/.cc-gh-config gh` for all `gh` commands

### Workflow
- **Commit after each substantive change** — don't batch unrelated changes into one big commit. Each logical change (feature, bugfix, refactor) gets its own commit.

### When the user says "remember"
Save the instruction to this CLAUDE.md file. Don't use auto-memory.

## Documentation surfaces & update checklist

| Information | Source of Truth | Propagated To |
|---|---|---|
| **CLI commands & flags** | ★ `cli.py` | README.md, website docs, CLAUDE.md |
| **Architecture** | ★ `CLAUDE.md` | website docs (architecture.md), README.md |
| **App download links** | ★ `website/src/data/apps.json` | `connection-info.html.j2` (CI-validated), `render.py:_PWA_APPS`, `app.js:osMap` |
| **Version** | ★ `VERSION` | importlib.metadata, website deploy, CHANGELOG.md |
| **SNI recommendations** | ★ `CLAUDE.md` conventions | website docs (deploy.md, troubleshooting.md) |

**New subcommand**: implement in `commands/`, register in `cli.py`, add test, update README.md, website docs, CLAUDE.md. AI docs auto-generated from human docs by CI (or run `make ai-docs` locally).

**New protocol**: add `InboundType` + `Protocol` subclass in `protocols.py`, add provisioner step, update `urls.py`, `render.py`, `display.py`, `connection-info.html.j2`, add tests, update website docs.

**New relay**: add `RelayEntry` in `credentials.py`, relay provisioner step, update `build_relay_urls()` in `urls.py`, update rendering, add tests.

## CI/CD

**Pipeline chain:** push → CI (9 jobs) → Release+Deploy (on CI success)

### CI jobs
Python Tests (3.10 + 3.12), Lint, Type Check, Validate (templates + app links + VERSION + CHANGELOG), Shell (shellcheck), Integration (3x-ui Docker), E2E Provisioner, Website Build

### Release
Deploy Pages (Astro build + CLI artifacts), GitHub Release (tag + notes from CHANGELOG), PyPI publish

### Versioning
- Patch (Z): fixes/docs → auto-updated
- Minor (Y): new features → prompted
- Major (X): breaking → prompted
- Always bump after completing work. Edit `VERSION` + `CHANGELOG.md`. One bump per session is fine.

## Codified patterns

1. **Protocol registry** — single source of truth, downstream code loops generically
2. **Credential lockout prevention** — persist locally BEFORE remote changes
3. **Versioned data formats** — auto-migration, preserve unknown fields
4. **Step pipeline** — composable, independently testable, `StepResult` status
5. **Shell injection defense** — `shlex.quote()` on all `conn.run()` values
6. **Server resolution cascade** — explicit IP > named server > local > auto-select > prompt > fail
7. **API quirk testing** — tests verify quirk is handled, named after the quirk
8. **Fail-with-context** — `fail()` includes hint_type + action items
9. **Idempotent provisioning** — every step checks state before acting
10. **Single source of truth** — every concern has exactly one canonical source
11. **Relay as infrastructure** — relay is L4 transparent, not a protocol; all protocols work through it via explicit SNI
12. **PWA shared + per-client split** — static assets shared; per-client files generated individually. `pwa.py` centralizes both.

## Backlog & tech debt

See `BACKLOG.md` for the full prioritized task list (includes Manual/External actions section for promotion and non-code work).
