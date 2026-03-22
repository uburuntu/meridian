---
title: Client Management
description: Add, list, and remove client access keys.
order: 5
section: guides
---

## Add a client

```
meridian client add alice
```

Each client gets their own unique connection key. The command generates:
- A **QR code** displayed in the terminal
- An **HTML connection page** saved locally
- A **shareable URL** (if server-hosted pages are enabled)

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
```

If you have only one server, it's auto-selected.

## How it works

Client names map to 3x-ui `email` fields with protocol prefixes:
- `reality-alice` — Reality inbound
- `xhttp-alice` — XHTTP inbound
- `wss-alice` — WSS inbound (domain mode)

Each client gets a unique UUID across all inbounds on the server.
