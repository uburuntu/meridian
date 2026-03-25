---
title: IP Blocked Recovery
description: What to do when your server's IP gets blocked — diagnosis and recovery options.
order: 7
section: guides
---

## Diagnose

Run from your local machine (no SSH needed):

```
meridian test IP
```

If the TCP port 443 check fails, the IP is likely blocked by your ISP or government. This is the most common issue in censored regions.

## Immediate relief

If you deployed with **domain mode** (`--domain`), your WSS/CDN connection still works — it routes through Cloudflare's CDN, bypassing the IP block entirely. Tell your users to switch to the WSS connection link on their connection page.

If you have a **relay** deployed, clients connecting through the relay are unaffected — they're connecting to the relay's domestic IP, not the blocked exit IP.

## Recovery options

### Option A: Deploy a new server

The fastest path if you have few clients and no relay:

```bash
# 1. Get a new VPS from your provider (new IP)
# 2. Deploy Meridian
meridian deploy NEW_IP

# 3. Re-add each client
meridian client add alice --server NEW_IP
meridian client add bob --server NEW_IP

# 4. Send new connection pages to your users
```

The deploy is idempotent — re-running on the same IP is safe and picks up where it left off.

### Option B: New exit server + existing relay

Best if you have a relay deployed — your clients keep their relay connection while you swap the exit server behind it:

```bash
# 1. Deploy new exit server
meridian deploy NEW_EXIT_IP

# 2. Re-add clients on new exit
meridian client add alice --server NEW_EXIT_IP
meridian client add bob --server NEW_EXIT_IP

# 3. Switch relay to new exit
meridian relay remove RELAY_IP --exit OLD_EXIT_IP
meridian relay deploy RELAY_IP --exit NEW_EXIT_IP

# Clients reconnect automatically — relay IP unchanged
```

### Option C: Add domain mode for CDN fallback

If you weren't using domain mode before, add it now to prevent future disruption:

```bash
meridian deploy NEW_IP --domain proxy.example.com
```

With domain mode, the WSS/CDN connection works even when the server IP is blocked — traffic routes through Cloudflare. See the [Domain mode guide](/docs/en/domain-mode/) for Cloudflare setup.

## Proactive defense

Set up resilience **before** your IP gets blocked:

1. **Deploy a relay** — gives clients a domestic entry point. When the exit IP is blocked, swap the exit behind the relay without touching clients:
   ```bash
   meridian relay deploy RELAY_IP --exit EXIT_IP
   ```

2. **Enable domain mode** — adds WSS/CDN fallback that works even if the IP is blocked:
   ```bash
   meridian deploy EXIT_IP --domain proxy.example.com
   ```

3. **Both** — maximum resilience. Clients have three paths: relay (domestic), CDN (Cloudflare), and direct (if unblocked).

## Client migration

Each client must be re-added manually on the new server — there is no automated migration tool yet. The workflow:

1. Deploy new server
2. `meridian client add NAME` for each client
3. Share new connection pages with users (QR code, shareable URL, or HTML file)

Connection pages are auto-generated with all available connection options (direct, relay, CDN). If you have server-hosted pages enabled, the shareable URLs update automatically.

## Keep your old server

Don't tear down the old server immediately — it may become unblocked after days or weeks. You can check periodically:

```bash
meridian test OLD_IP
```

If it comes back, you have a spare exit server ready to go.
