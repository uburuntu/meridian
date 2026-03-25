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

## How it works

Client names map to 3x-ui `email` fields with protocol prefixes:
- `reality-alice` — Reality inbound
- `xhttp-alice` — XHTTP inbound
- `wss-alice` — WSS inbound (domain mode)

Each client gets a unique UUID across all inbounds on the server.
