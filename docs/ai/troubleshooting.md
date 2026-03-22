# Meridian — Troubleshooting Guide

## Which Tool to Use

```
BEFORE INSTALL           → meridian preflight IP
  "Will this server work for Meridian?"
  Tests: SNI reachability, port 443, DNS, OS, disk space.

AFTER INSTALL, CAN'T CONNECT → meridian test IP
  "Is the proxy reachable from where I am right now?"
  Tests: TCP port 443, TLS handshake (Reality), domain HTTPS.
  No SSH needed — runs from the client device.

AFTER INSTALL, SOMETHING BROKE → meridian doctor IP
  "Collect everything for debugging."
  Collects: server OS, Docker, 3x-ui logs, ports, firewall, SNI, DNS.

Add --ai to preflight or doctor for an AI-ready prompt.
```

## Symptom: Can't Connect at All

### Port 443 not reachable (test fails on TCP check)

**Causes:**
1. Cloud provider firewall / security group blocks port 443 inbound
2. ISP or network blocks the server IP entirely
3. Server is down or proxy is not running
4. UFW on the server doesn't allow port 443

**Fixes:**
1. Check cloud provider console — ensure port 443/TCP is allowed inbound
2. Try from a different network (mobile data, another Wi-Fi) to rule out local ISP blocking
3. SSH into the server and check: `docker ps` (is 3x-ui running?), `ss -tlnp sport = :443` (is anything listening?)
4. Check UFW: `ufw status` — should show 443/tcp ALLOW

### TLS handshake fails (test passes TCP but fails TLS)

**Causes:**
1. Xray is not running inside the Docker container
2. Port 443 is occupied by another service (not Xray/HAProxy)
3. Reality SNI target is unreachable from the server (breaks Reality protocol)

**Fixes:**
1. Check Xray: `docker logs 3x-ui --tail 20` — look for errors
2. Check what's on port 443: `ss -tlnp sport = :443` — should be xray, haproxy, or 3x-ui
3. Test SNI target: `meridian preflight IP --sni www.microsoft.com`

### Domain not reachable (test passes Reality but fails domain HTTPS)

**Causes:**
1. DNS not pointing to server IP
2. Caddy not running or failed to get TLS certificate
3. HAProxy not routing domain SNI correctly

**Fixes:**
1. Check DNS: `dig +short yourdomain.com @8.8.8.8` — should return server IP
2. Check Caddy: `systemctl status caddy`, `journalctl -u caddy --no-pager -n 20`
3. Check HAProxy: `systemctl status haproxy`, look at `/etc/haproxy/haproxy.cfg`

## Symptom: Connection Drops After a Few Seconds

**Causes:**
1. System clock skew >30 seconds between client device and server
2. MTU issues on the network path
3. ISP performing connection reset after detecting long-lived TLS sessions

**Fixes:**
1. Sync clock: on server `timedatectl set-ntp true`, on client device check automatic time setting
2. Try a different network to rule out MTU/ISP issues
3. In domain mode, try the WSS/CDN connection link — it routes through Cloudflare and avoids direct IP detection

## Symptom: Setup Fails

### Port 443 conflict

**Cause:** Another service (Apache, Nginx, etc.) is using port 443.

**Fix:** Stop the conflicting service or run Meridian on a clean server. `meridian preflight IP` will tell you what's using the port.

### Xray fails to start (invalid JSON / MarshalJSON error)

**Cause:** The 3x-ui inbound `settings` or `streamSettings` fields contain corrupted JSON. This happens when the `settings` field is sent as a nested object instead of a JSON string — the 3x-ui Go struct expects a `string` type for these fields. The API returns `success: true` but stores only the first key name (e.g., `"clients"`) instead of the full JSON object.

**Fix:** `PanelClient` always sends `settings` as a JSON string inside the JSON body (double-serialized). If you hit this on an older version, uninstall and reinstall: `meridian teardown IP && meridian deploy IP`. To verify the database is clean: `sqlite3 /opt/3x-ui/db/x-ui.db "SELECT settings FROM inbounds;"` — each field should be valid JSON, not a single word.

### XHTTP inbound creation fails (port already exists)

**Cause:** In standalone mode, both Reality TCP and XHTTP tried to bind port 443. 3x-ui rejects duplicate ports.

**Fix:** Fixed in v1.2.1. XHTTP now uses a separate dedicated port (`xhttp_port` variable). The port is deterministic (seeded by hostname) and automatically opened in UFW.

### Docker installation fails

**Cause:** Conflicting Docker packages (docker.io, containerd from distro repos).

**Fix:** Meridian auto-removes conflicting packages, but if Docker is already running with containers, it skips installation to avoid disruption. Remove old Docker manually if needed: `apt remove docker.io containerd runc`

### Disk space insufficient

**Cause:** Less than 2GB free disk space.

**Fix:** Free up space: `docker system prune -af`, `journalctl --vacuum-time=1d`, check for large files in `/var/log/`

### DNS resolution fails (domain mode)

**Cause:** Domain doesn't resolve to server IP yet.

**Fix:** Update DNS A record to point to server IP. DNS propagation can take up to 48 hours but usually 5-15 minutes. Meridian will warn you if DNS doesn't resolve but lets you proceed.

### SSH connection errors

**Cause:** SSH key not accepted, server unreachable, or wrong user.

**Fix:** Test SSH manually: `ssh root@SERVER_IP`. Ensure you have key-based access (not just password). Use `--user` flag if not root.

## Symptom: Was Working, Now Stopped

**Causes:**
1. Server IP got blocked by ISP/government — very common in censored regions
2. Server rebooted and Docker didn't auto-start
3. Let's Encrypt certificate expired (domain mode, rare — Caddy auto-renews)
4. 3x-ui database grew too large (unlikely — weekly cron vacuum)

**Fixes:**
1. Run `meridian test IP` — if TCP fails, the IP is likely blocked. Use the WSS/CDN link (domain mode) or deploy a new server
2. SSH in and check: `docker ps` — if 3x-ui is not listed, run `docker start 3x-ui`
3. Check Caddy logs: `journalctl -u caddy --no-pager -n 20`
4. Check disk: `df -h /`

## Symptom: Slow Speeds

**Causes:**
1. Geographic distance between user and server (high latency)
2. Server overloaded (too many clients, high CPU)
3. ISP throttling VPN-like traffic patterns
4. Suboptimal routing

**Fixes:**
1. Choose a server geographically closer to users. Recommended: Finland, Netherlands, Sweden, Germany for Europe/Middle East
2. Check server load: `htop` or `uptime`. Consider a higher-spec VPS
3. Try WSS/CDN link (domain mode) — routes through Cloudflare, may have better routing
4. Enable BBR (Meridian enables it by default): verify with `sysctl net.ipv4.tcp_congestion_control`

## SNI Target Selection

The SNI target is the domain that Reality impersonates. Choosing the wrong one can increase detection risk, though current evidence (IMC 2022, net4people, 2026 research) shows censors rely more on behavioral analysis than IP→domain validation.

**Good SNI targets** (global CDN, shared hosting infrastructure):
- `www.microsoft.com` (default) — Azure CDN, global presence
- `www.twitch.tv` — Fastly CDN, global
- `dl.google.com` — Google CDN, global
- `github.com` — Fastly CDN, global

**Bad SNI targets** (proprietary ASN):
- `apple.com`, `icloud.com` — Apple controls its own ASN ranges. IP/ASN mismatch is a known research-identified detection vector.
- Small/niche single-IP websites — unusual for a VPS IP to serve them.

**Options for SNI selection:**
1. **Global CDN domain** (default) — safe, widely used, no ASN mismatch with major CDN providers
2. **Same-network domain** via `meridian scan` — finds domains on your subnet for ASN consistency
3. **Self-steal** (your own domain) — run a real website, use Reality to masquerade as yourself. Eliminates all IP/ASN/cert mismatches. Requires domain mode (`--domain`). Meridian's domain mode partially supports this — future versions may add full self-steal.

**What actually matters more than SNI choice:** The real detection threat in 2026 is post-handshake behavioral analysis (traffic patterns, packet timing, session duration). XHTTP transport (`--xhttp`) directly addresses this by making tunnel traffic look like normal HTTP browsing. SNI choice is secondary.

## Interpreting `meridian preflight` Output

| Check | What It Tests | If It Fails |
|-------|--------------|-------------|
| SNI target reachability | Can the server reach the camouflage site (e.g., microsoft.com)? | Server's outbound is restricted. Try a different SNI target with `--sni` |
| SNI ASN match | Does the SNI target share a CDN/ASN with the server? | Use a global CDN domain (microsoft.com, twitch.tv, github.com). Avoid apple.com (Apple-owned ASN, instant detection) |
| Port 443 availability | Is port 443 free or used by Meridian? | Another service is on 443. Stop it or use a clean server |
| Port 443 external reachability | Can the outside world reach port 443? | Cloud firewall blocks it. Open port 443/TCP inbound |
| Domain DNS | Does the domain resolve to server IP? | Update DNS A record |
| Server OS | Is it Ubuntu/Debian? | Other distros may work but are untested |
| Disk space | At least 2GB free? | Free up space |

## Interpreting `meridian doctor` Output

| Section | What to Look For |
|---------|-----------------|
| Local Machine | OS compatibility |
| Server | OS version, uptime (recent reboot?), disk/memory usage |
| Docker | Is 3x-ui container running? Status should be "Up" |
| 3x-ui Logs | Error messages, "failed to start" entries, certificate issues |
| Listening Ports | Port 443 should show xray, haproxy, or 3x-ui. If missing, proxy isn't running |
| Firewall (UFW) | Port 443/tcp should be ALLOW. If not listed, it's blocked |
| SNI Target | Should show CONNECTED with a certificate chain. If unreachable, Reality can't work |
| Domain DNS | Should resolve to server IP. If different or empty, DNS is misconfigured |

## Interpreting `meridian test` Output

| Check | Pass | Fail |
|-------|------|------|
| TCP port 443 | Server is network-reachable | Firewall, ISP block, or server down |
| TLS handshake | Reality protocol is working | Xray not running, port conflict, or SNI issue |
| Domain HTTPS | Caddy + HAProxy working | DNS, Caddy, or HAProxy issue |

**If all test checks pass but VPN client still can't connect:**
- Re-scan the QR code or re-import the VLESS link
- Ensure device clock is accurate (within 30 seconds)
- Try a different VPN app (v2rayNG, Hiddify)
- Check that the app is using the Reality link, not an old/invalid one
