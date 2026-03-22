---
title: CLI Reference
description: Complete reference for all Meridian CLI commands and flags.
order: 8
section: reference
---

## Commands

### meridian deploy

Deploy proxy server to a VPS.

```
meridian deploy [IP] [flags]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--sni HOST` | www.microsoft.com | Site that Reality impersonates |
| `--domain DOMAIN` | (none) | Enable domain mode with CDN fallback |
| `--email EMAIL` | (none) | Email for TLS certificates |
| `--xhttp / --no-xhttp` | enabled | XHTTP transport |
| `--name NAME` | default | Name for the first client |
| `--user USER` | root | SSH user |
| `--yes` | | Skip confirmation prompts |

### meridian client

Manage client access keys.

```
meridian client add NAME [--server NAME]
meridian client list [--server NAME]
meridian client remove NAME [--server NAME]
```

### meridian server

Manage known servers.

```
meridian server add [IP]
meridian server list
meridian server remove NAME
```

### meridian preflight

Pre-flight server validation. Tests SNI, ports, DNS, OS, disk, ASN without installing anything.

```
meridian preflight [IP] [--ai] [--server NAME]
```

### meridian scan

Find optimal SNI targets on the server's network using RealiTLScanner.

```
meridian scan [IP] [--server NAME]
```

### meridian test

Test proxy reachability from the client device. No SSH needed.

```
meridian test [IP] [--server NAME]
```

### meridian doctor

Collect system diagnostics for debugging. Alias: `meridian rage`.

```
meridian doctor [IP] [--ai] [--server NAME]
```

### meridian teardown

Remove proxy from server.

```
meridian teardown [IP] [--server NAME] [--yes]
```

### meridian update

Update CLI to latest version.

```
meridian update
```

### meridian --version

Show CLI version.

```
meridian --version
meridian -v
```

## Global flags

| Flag | Description |
|------|-------------|
| `--server NAME` | Target a specific named server |

## Server resolution

Commands that need a server follow this priority:
1. Explicit IP argument
2. `--server NAME` flag
3. Local mode detection (running on the server itself)
4. Single server auto-select (if only one saved)
5. Interactive prompt
