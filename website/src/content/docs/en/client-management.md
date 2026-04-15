---
title: Client Management
description: Add users, share connection details, and manage access keys.
order: 5
section: guides
---

## Add a client

```
meridian client add alice
```

This creates a unique connection key for "alice" and displays:
- A **QR code** in the terminal — scan it with a VPN app to connect instantly
- **Connection URLs** — VLESS links for each protocol (Reality, XHTTP, and WSS if domain mode is enabled)
- A **shareable page URL** — hosted on your server, ready to send via any messenger
- An **HTML file** saved locally — backup for offline sharing

### What the recipient sees

The shareable URL opens a connection page with:
- Step-by-step instructions for installing a VPN app (v2RayTun, v2rayNG, Hiddify, or v2rayN)
- QR codes for each connection protocol
- One-tap "Open in App" deep links
- Connection status and usage stats

Send the URL by email, iMessage, Telegram, or any messenger. The recipient opens it, installs the app, scans the QR code, and connects. No technical knowledge needed.

## Show connection details

To re-display connection info for an existing client at any time:

```
meridian client show alice
```

This outputs the same QR code, connection URLs, and shareable page link — without creating a new key. Use this when:
- You need to re-share the connection page with someone
- You lost the original QR code or HTML file
- You want to verify what a client's connection looks like

## List clients

```
meridian client list
```

Shows all clients with their protocol connections (Reality, XHTTP, WSS).

## Remove a client

```
meridian client remove alice
```

Revokes access immediately. The client's UUID is removed from all inbounds on the server.

## Multi-server

Use `--server` to target a specific named server:

```
meridian client add alice --server finland
meridian client show alice --server finland
meridian client list --server finland
```

If you have only one server, it's auto-selected.

## Where credentials are stored

When you run `meridian deploy` from your laptop, Meridian saves server credentials locally:

```
~/.meridian/credentials/<IP>/proxy.yml   # keys, UUIDs, panel access
~/.meridian/servers                      # server registry
```

On the server itself, the same data lives in `/etc/meridian/proxy.yml`. Meridian syncs between them automatically after `client add` and `client remove`.

This is why `meridian client add alice` works without specifying the server — Meridian looks it up in the local registry. If you have multiple servers, use `--server NAME`.

If credentials get out of sync (e.g. you added a client from a different machine), `client show` will recover the data from the server panel automatically.

## Web panel

Meridian deploys a 3x-ui management panel for traffic monitoring. Access it at the secret HTTPS path shown in your credentials:

```
cat ~/.meridian/credentials/<IP>/proxy.yml | grep -A5 panel
```

The panel URL, username, and password are listed there. No SSH tunnel needed — nginx reverse-proxies the panel at a randomized HTTPS path.

## How it works

Client names map to 3x-ui `email` fields with protocol prefixes:
- `reality-alice` — Reality inbound
- `xhttp-alice` — XHTTP inbound
- `wss-alice` — WSS inbound (domain mode)

Each client gets a unique UUID across all inbounds on the server.

## Declarative client list

For fleet-wide setups you can manage clients declaratively instead of imperatively. Add a `desired_clients` list to `~/.meridian/cluster.yml`:

```yaml
desired_clients:
  - alice
  - bob
  - charlie
```

Then `meridian plan` shows the diff against the panel's actual user list, and `meridian apply` converges — adds any missing clients, removes any extra ones. `meridian client add/remove` still works alongside this; the two approaches coexist. See the [declarative workflow](/docs/en/getting-started/#declarative-workflow) for the full story.
