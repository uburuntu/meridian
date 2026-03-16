# Meridian

Ansible automation for deploying censorship-resistant proxy servers. Bypasses DPI, active probing, TLS fingerprinting, and IP whitelisting.

## What This Does

Deploys fully configured proxy servers on fresh Debian/Ubuntu VPS instances with one command. Supports both direct connections and a two-server relay chain for IP whitelist bypass.

**Three modes:**

| Mode | Command | What You Get |
|------|---------|--------------|
| **Standalone** | `ansible-playbook playbook.yml` | Single server with VLESS+Reality on port 443 |
| **Standalone + Domain** | `ansible-playbook playbook.yml -e domain=...` | + CDN fallback + decoy site |
| **Chain (Exit + Relay)** | `ansible-playbook -i inventory-chain.yml playbook-chain.yml` | Two-server relay chain for IP whitelist bypass |

## Architecture

```
No-domain mode:
  Port 443 → Xray VLESS+Reality (impersonates microsoft.com)
  Port [random] → 3x-ui panel (HTTP)

Domain mode:
  Port 443 → HAProxy (SNI router, no TLS termination)
               ├── SNI=microsoft.com → Xray Reality (127.0.0.1:10443)
               └── SNI=your-domain   → Caddy (127.0.0.1:8443)
                                        ├── /           → decoy website
                                        ├── /[secret]   → WSS proxy → Xray
                                        ├── /[secret]   → 3x-ui panel
                                        └── /[secret]   → connection info page
  Port 80  → Caddy (ACME + redirect)

Chain mode (bypass IP whitelisting):
  User → Russian Relay VPS (whitelisted IP, VLESS+TCP, no TLS)
       → German Exit VPS (VLESS+Reality+XHTTP on port 443)
       → Internet

  Exit Node:
    Port 443  → Xray VLESS+Reality+XHTTP (relay connects here)
    Port 8444 → Xray VLESS+Reality+TCP (direct user fallback)

  Relay Node:
    Port 443  → Xray VLESS+TCP (user connects, no TLS)
    Routing:    Russian sites → DIRECT, everything else → exit chain
```

## Prerequisites

**On the server:** A fresh Debian 12 or Ubuntu 22.04+ VPS with root SSH key access. At least 1GB RAM.

**On your machine:** macOS or Linux with `curl` and `ssh`. The setup script installs everything else (Ansible, qrencode) automatically.

## Quick Start

One command. It installs dependencies, configures the server, and outputs a QR code.

```bash
curl -sS https://raw.githubusercontent.com/rmbk/meridian/main/setup.sh | bash
```

Or pass the server IP directly:

```bash
curl -sS https://raw.githubusercontent.com/rmbk/meridian/main/setup.sh | bash -s -- 203.0.113.42
```

With a domain (adds a decoy website + CDN fallback):

```bash
curl -sS https://raw.githubusercontent.com/rmbk/meridian/main/setup.sh | bash -s -- 203.0.113.42 --domain example.com
```

The script outputs an HTML file with a QR code. Send it to whoever needs it — they scan, connect, done.

### Manual Setup (Full Control)

If you prefer managing the Ansible project directly:

```bash
git clone https://github.com/rmbk/meridian.git && cd meridian
pip3 install ansible
ansible-galaxy collection install -r requirements.yml
# Edit inventory.yml with your server IP
ansible-playbook playbook.yml
```

### Chain Mode (IP Whitelist Bypass)

Two-server relay chain for when direct foreign connections are blocked:

```bash
git clone https://github.com/rmbk/meridian.git && cd meridian
cp inventory-chain.yml.example inventory-chain.yml
# Edit with both server IPs (exit abroad + relay domestic)
ansible-playbook -i inventory-chain.yml playbook-chain.yml
```

The exit node is configured first, then its credentials are automatically passed to the relay.

### 4. Connect Your Device

The playbook outputs:
- QR codes in the terminal (scan with your phone)
- VLESS connection URLs (copy/paste into client app)
- A self-contained HTML file in `credentials/` (send to your friend)
- If domain mode: a web page at `https://your-domain/[secret-path]`

## Client Apps

| Platform | App | Link |
|----------|-----|------|
| iOS | v2RayTun | [App Store](https://apps.apple.com/app/v2raytun/id6476628951) |
| Android | v2rayNG | [Play Store](https://play.google.com/store/apps/details?id=com.v2ray.ang) |
| All | Hiddify | [GitHub](https://github.com/hiddify/hiddify-app/releases/latest) |
| Windows | v2rayN | [GitHub](https://github.com/2dust/v2rayN/releases/latest) |

## Cloudflare CDN Setup (Domain Mode Only)

The CDN fallback routes traffic through Cloudflare, making the connection resistant to IP blocking.

**Important: Follow this exact order to avoid TLS certificate issues.**

### First-time setup:

1. Add your domain in the [Cloudflare dashboard](https://dash.cloudflare.com)
2. Create an **A record** pointing to your server IP
3. **Keep the cloud icon grey** ("DNS only" mode) — do NOT enable proxy yet
4. Run the playbook: `ansible-playbook playbook.yml -e domain=...`
5. Wait for Caddy to obtain the TLS certificate (automatic, takes ~30 seconds)

### After the playbook succeeds:

6. In Cloudflare, **click the cloud icon to turn it orange** (enable Proxy)
7. Go to **SSL/TLS** settings, set mode to **Full (Strict)**
8. Go to **Network** settings, **enable WebSockets**
9. In **SSL/TLS > Edge Certificates**, disable "Always Use HTTPS" (or add a page rule to exclude `/.well-known/acme-challenge/*`)

> **Why this order?** Caddy obtains TLS certificates via HTTP-01 challenge on port 80. If Cloudflare's proxy is active with "Always Use HTTPS", it redirects the ACME challenge to HTTPS, which breaks certificate issuance. Once the initial certificate is obtained, renewals work fine because Caddy caches the certificate and renews in the background.

## Customization

Edit `group_vars/all.yml` to change:

| Variable | Default | Description |
|----------|---------|-------------|
| `reality_sni` | `www.microsoft.com` | Website Reality impersonates |
| `utls_fingerprint` | `chrome` | TLS client fingerprint |
| `client_limit_ip` | `2` | Max simultaneous IPs per client |
| `ssh_disable_password` | `true` | Disable SSH password auth |
| `bbr_enabled` | `true` | Enable BBR congestion control |
| `decoy_site_title` | `Meridian Digital Solutions` | Decoy website name |

### Multiple Servers

Add more hosts to `inventory.yml`:

```yaml
all:
  hosts:
    server1:
      ansible_host: "203.0.113.42"
    server2:
      ansible_host: "203.0.113.43"
      reality_sni: "www.apple.com"
```

Each server gets its own credentials file in `credentials/`.

## Operations

### Update 3x-ui and Xray

```bash
ssh root@your-server
cd /opt/3x-ui && docker compose pull && docker compose down && docker compose up -d
```

### Re-run Safely

The playbook is fully idempotent. Running it again will:
- Skip Docker installation if containers are running
- Skip credential generation (loaded from local file)
- Skip inbound creation if they already exist
- Only reload configs that changed

```bash
ansible-playbook playbook.yml  # safe to re-run
```

### Add Users

Use the 3x-ui panel web interface to add more clients to existing inbounds.

## Troubleshooting

**Connection fails immediately:**
- Check that your device clock is accurate within 30 seconds
- Enable "Set Automatically" for date/time on your device

**Connection works then stops after days:**
- The server IP may have been blocked
- Switch to the CDN fallback configuration
- Or get a new IP from your hosting provider and re-run the playbook

**Slow speeds on Hetzner:**
- Some Hetzner IP ranges are throttled by Russian ISPs
- Consider Contabo, Netcup, or servers in Finland/Netherlands/Sweden

**Do NOT run other VPN protocols** (OpenVPN, WireGuard, etc.) on this server. They will get the entire IP flagged and blocked, taking down your Reality connection with it.

### SNI Target Selection

The default `www.microsoft.com` works well. For optimal stealth, the SNI target should:
- Support TLS 1.3 + HTTP/2
- Not be behind Cloudflare
- Be geographically close to your server
- Be high-traffic (not suspicious)

Good alternatives: `www.apple.com`, `dl.google.com`, `www.yahoo.com`

Use [RealiTLScanner](https://github.com/XTLS/RealiTLScanner) to find optimal targets in your server's datacenter.

## Security Notes

- Credentials are saved locally in `credentials/` (git-ignored)
- **No-domain mode:** The 3x-ui panel binds to `127.0.0.1` only — it is NOT exposed to the internet. Access it exclusively via SSH tunnel: `ssh -L 2053:127.0.0.1:2053 root@SERVER_IP`, then open `http://127.0.0.1:2053/SECRET_PATH/`
- **Domain mode:** The panel is proxied through Caddy with HTTPS on a secret path
- SSH password authentication is disabled by default
- UFW firewall allows only ports 22 and 443 (plus 80 in domain mode for ACME)
- Automatic security updates are enabled
- The 3x-ui container runs with `network_mode: host` as required by Xray — this is the standard deployment method
