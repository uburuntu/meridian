---
title: Installation
description: Install the Meridian CLI on your local machine.
order: 2
section: guides
---

## Quick install

```
curl -sSf https://getmeridian.org/install.sh | bash
```

This script:
1. Installs [uv](https://docs.astral.sh/uv/) if not present (or uses pipx as fallback)
2. Installs `meridian-vpn` from PyPI
3. Creates a symlink at `/usr/local/bin/meridian` for system-wide access
4. Migrates from the old bash-based CLI if present

## Manual install

With uv (recommended):
```
uv tool install meridian-vpn
```

With pipx:
```
pipx install meridian-vpn
```

## Update

```
meridian update
```

Meridian checks for updates automatically:
- **Patch versions** (bug fixes) — installed silently
- **Minor versions** (new features) — you're prompted to update
- **Major versions** (breaking changes) — you're prompted to update

## Requirements

- **Python 3.10+** (installed automatically by uv/pipx)
- **SSH key access** to your target server
- **qrencode** (optional, for terminal QR codes): `brew install qrencode` or `apt install qrencode`

## Verify installation

```
meridian --version
```
