"""HAProxy, Caddy, and connection page provisioning steps.

Replaces roles/haproxy/tasks/main.yml, roles/caddy/tasks/main.yml,
and the connection page deployment from roles/caddy/tasks/main.yml.
"""

from __future__ import annotations

import shlex
import textwrap
import time
from dataclasses import dataclass
from typing import Any

from meridian.ssh import ServerConnection

# ---------------------------------------------------------------------------
# StepResult — local definition matching the pattern from steps.py
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    name: str
    status: str  # "ok" | "changed" | "skipped" | "failed"
    detail: str = ""
    duration_ms: int = 0


def _timed(fn):  # noqa: ANN001, ANN202
    """Decorator that adds duration_ms to the returned StepResult."""

    def wrapper(*args: Any, **kwargs: Any) -> StepResult:
        t0 = time.monotonic()
        result = fn(*args, **kwargs)
        result.duration_ms = int((time.monotonic() - t0) * 1000)
        return result

    return wrapper


# ---------------------------------------------------------------------------
# HAProxy configuration template
# ---------------------------------------------------------------------------


def _render_haproxy_cfg(
    reality_sni: str,
    haproxy_reality_backend_port: int,
    caddy_internal_port: int,
) -> str:
    """Render the HAProxy configuration.

    Replaces: roles/haproxy/templates/haproxy.cfg.j2

    HAProxy sits on port 443 and does TCP-level SNI routing WITHOUT
    TLS termination. Reality-targeted SNIs go to Xray, everything
    else goes to Caddy.
    """
    return textwrap.dedent(f"""\
        # HAProxy SNI Router
        # Managed by Meridian. Manual edits will be overwritten on next run.
        #
        # Flow:
        #   Client with SNI={reality_sni} -> Xray Reality (127.0.0.1:{haproxy_reality_backend_port})
        #   Client with any other SNI      -> Caddy HTTPS  (127.0.0.1:{caddy_internal_port})

        global
            log /dev/log local0
            log /dev/log local1 notice
            chroot /var/lib/haproxy
            stats socket /run/haproxy/admin.sock mode 660 level admin
            stats timeout 30s
            user haproxy
            group haproxy
            daemon
            maxconn 4096

        defaults
            mode tcp
            log global
            option tcplog
            option dontlognull
            timeout connect 5s
            timeout client  300s
            timeout server  300s
            retries 3

        # --- Port 443: SNI-based TLS routing ---
        frontend tls_router
            bind *:443
            # Wait up to 5s to inspect the TLS ClientHello for SNI
            tcp-request inspect-delay 5s
            tcp-request content accept if {{ req_ssl_hello_type 1 }}

            # Route connections with Reality SNI to Xray
            use_backend xray_reality if {{ req_ssl_sni -i {reality_sni} }}

            # Everything else (user's domain, unknown SNI) goes to Caddy
            default_backend caddy_https

        # --- Backend: Xray Reality ---
        backend xray_reality
            server xray 127.0.0.1:{haproxy_reality_backend_port}

        # --- Backend: Caddy HTTPS ---
        backend caddy_https
            server caddy 127.0.0.1:{caddy_internal_port}
    """)


# ---------------------------------------------------------------------------
# Caddy configuration template
# ---------------------------------------------------------------------------


def _render_caddy_config(
    domain: str,
    caddy_internal_port: int,
    ws_path: str,
    wss_internal_port: int,
    panel_web_base_path: str,
    panel_internal_port: int,
    info_page_path: str,
    email: str = "",
) -> str:
    """Render the Meridian Caddy configuration.

    Replaces: roles/caddy/templates/Caddyfile.j2

    Architecture: HAProxy (port 443) -> Caddy (internal port)
    HAProxy terminates nothing -- just routes by SNI. Caddy handles TLS.
    """
    tls_line = f"    tls {email}\n" if email else ""

    return textwrap.dedent(f"""\
        # Meridian Proxy Configuration
        # Managed by Meridian -- this file is overwritten on each run.
        # Your own Caddy config in /etc/caddy/Caddyfile is NOT touched.
        #
        # Architecture: HAProxy (port 443) -> Caddy (port {caddy_internal_port})
        # HAProxy terminates nothing -- just routes by SNI. Caddy handles TLS.

        {domain}:{caddy_internal_port} {{
        {tls_line}
            # --- VLESS+WSS Fallback (Cloudflare CDN path) ---
            handle /{ws_path} {{
                reverse_proxy 127.0.0.1:{wss_internal_port} {{
                    transport http {{
                        read_timeout 360s
                    }}
                }}
            }}

            # --- 3x-ui Panel (management interface on secret path) ---
            handle /{panel_web_base_path}/* {{
                reverse_proxy 127.0.0.1:{panel_internal_port}
            }}

            # --- Connection Info Page (QR codes and setup instructions) ---
            handle /{info_page_path} {{
                rewrite * /index.html
                root * /var/www/private
                file_server
                header Cache-Control "no-store"
            }}

            # --- Per-client stats (fetched by connection info page JS) ---
            handle /{info_page_path}/stats/* {{
                uri strip_prefix /{info_page_path}
                root * /var/www/private
                file_server
                header Cache-Control "no-store, max-age=0"
                header Access-Control-Allow-Origin *
            }}

            header -Server
            header X-Content-Type-Options "nosniff"
            header X-Frame-Options "DENY"
            header Referrer-Policy "no-referrer"

            log {{
                output file /var/log/caddy/access.log {{
                    roll_size 10mb
                    roll_keep 3
                }}
            }}
        }}

        http://{domain} {{
            redir https://{domain}{{uri}} permanent
        }}
    """)


# ---------------------------------------------------------------------------
# Stats update script template
# ---------------------------------------------------------------------------


def _render_stats_script(panel_internal_port: int) -> str:
    """Render the stats update Python script.

    Replaces: roles/caddy/templates/update-stats.py.j2
    """
    return textwrap.dedent(f"""\
        #!/usr/bin/env python3
        \"\"\"Fetch per-client traffic stats from 3x-ui and write per-client JSON files.

        Each client gets a stats file named by their Reality UUID -- the same UUID
        that appears in their VLESS connection URL. Only someone with the URL can
        find their stats file. Runs via cron every 5 minutes.
        \"\"\"
        import json, urllib.request, http.cookiejar, os, time, sys

        CREDS = '/etc/meridian/proxy.yml'
        STATS_DIR = '/var/www/private/stats'

        def parse_creds():
            \"\"\"Parse v2 nested YAML credentials.\"\"\"
            import json as _json
            creds = {{}}
            with open(CREDS) as f:
                content = f.read()
            try:
                import importlib
                _yaml = importlib.import_module('yaml')
                data = _yaml.safe_load(content)
                if isinstance(data, dict):
                    panel = data.get('panel', {{}})
                    creds['panel_username'] = panel.get('username', '')
                    creds['panel_password'] = panel.get('password', '')
                    creds['panel_web_base_path'] = panel.get('web_base_path', '')
            except ImportError:
                with open(CREDS) as f:
                    for line in f:
                        line = line.strip()
                        if ':' in line and not line.startswith('#') and not line.startswith('-'):
                            key, val = line.split(':', 1)
                            creds[key.strip()] = val.strip().strip('"')
            return creds

        def main():
            creds = parse_creds()
            wbp = creds.get('panel_web_base_path', '')
            base = f"http://127.0.0.1:{panel_internal_port}/{{wbp}}"

            cj = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
            login_data = f"username={{creds['panel_username']}}&password={{creds['panel_password']}}".encode()
            try:
                opener.open(urllib.request.Request(f"{{base}}/login", data=login_data, method='POST'))
            except Exception:
                sys.exit(1)

            try:
                resp = opener.open(f"{{base}}/panel/api/inbounds/list")
                inbounds = json.load(resp)
            except Exception:
                sys.exit(1)

            if not inbounds.get('success'):
                sys.exit(1)

            clients = {{}}
            for inbound in inbounds.get('obj', []):
                settings = json.loads(inbound['settings'])
                for client in settings.get('clients', []):
                    email = client['email']
                    uuid = client['id']
                    if email.startswith('reality-'):
                        name = email[8:]
                        clients.setdefault(name, {{}})['reality_uuid'] = uuid
                        clients[name].setdefault('emails', []).append(email)
                    elif email.startswith('wss-'):
                        name = email[4:]
                        clients.setdefault(name, {{}})
                        clients[name].setdefault('emails', []).append(email)

            os.makedirs(STATS_DIR, exist_ok=True)

            active_uuids = set()
            for name, info in clients.items():
                uuid = info.get('reality_uuid')
                if not uuid:
                    continue
                active_uuids.add(uuid)

                total_up = 0
                total_down = 0
                last_online = 0

                for email in info.get('emails', []):
                    try:
                        resp = opener.open(f"{{base}}/panel/api/inbounds/getClientTraffics/{{email}}")
                        data = json.load(resp)
                        if data.get('success') and data.get('obj'):
                            obj = data['obj']
                            total_up += obj.get('up', 0)
                            total_down += obj.get('down', 0)
                            lo = obj.get('lastOnline', 0)
                            if lo > last_online:
                                last_online = lo
                    except Exception:
                        pass

                stats = {{
                    'up': total_up,
                    'down': total_down,
                    'total': total_up + total_down,
                    'lastOnline': last_online,
                    'updated': int(time.time() * 1000)
                }}
                path = os.path.join(STATS_DIR, f"{{uuid}}.json")
                with open(path, 'w') as f:
                    json.dump(stats, f)
                os.chmod(path, 0o644)

            for fname in os.listdir(STATS_DIR):
                if fname.endswith('.json'):
                    uid = fname[:-5]
                    if uid not in active_uuids:
                        os.remove(os.path.join(STATS_DIR, fname))

        if __name__ == '__main__':
            main()
    """)


# ---------------------------------------------------------------------------
# InstallHAProxy
# ---------------------------------------------------------------------------


class InstallHAProxy:
    """Install HAProxy and deploy SNI routing configuration.

    Replaces: roles/haproxy/tasks/main.yml + haproxy.cfg.j2

    HAProxy sits on port 443 and inspects the TLS ClientHello SNI field
    WITHOUT terminating TLS. Routes Reality-targeted SNIs to Xray,
    everything else to Caddy.
    """

    name = "install_haproxy"

    def __init__(
        self,
        reality_sni: str,
        haproxy_reality_backend_port: int = 10443,
        caddy_internal_port: int = 8443,
    ) -> None:
        self.reality_sni = reality_sni
        self.haproxy_reality_backend_port = haproxy_reality_backend_port
        self.caddy_internal_port = caddy_internal_port

    @_timed
    def run(self, conn: ServerConnection, ctx: dict[str, Any]) -> StepResult:
        # Check if already installed and configured
        check = conn.run("dpkg -l haproxy 2>/dev/null | grep -q '^ii'", timeout=10)
        already_installed = check.returncode == 0

        # Install HAProxy
        if not already_installed:
            result = conn.run(
                "DEBIAN_FRONTEND=noninteractive apt-get install -y haproxy",
                timeout=120,
            )
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"Failed to install HAProxy: {result.stderr.strip()}",
                )

        # Render and deploy configuration
        config = _render_haproxy_cfg(
            reality_sni=self.reality_sni,
            haproxy_reality_backend_port=self.haproxy_reality_backend_port,
            caddy_internal_port=self.caddy_internal_port,
        )
        q_config = shlex.quote(config)
        result = conn.run(f"printf '%s' {q_config} > /etc/haproxy/haproxy.cfg", timeout=10)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to write HAProxy config: {result.stderr.strip()}",
            )

        # Validate configuration
        result = conn.run("haproxy -c -f /etc/haproxy/haproxy.cfg", timeout=10)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"HAProxy config validation failed: {result.stderr.strip()}",
            )

        # Start/enable/reload HAProxy
        conn.run("systemctl enable haproxy", timeout=10)
        result = conn.run("systemctl reload-or-restart haproxy", timeout=15)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to start HAProxy: {result.stderr.strip()}",
            )

        status = "changed" if not already_installed else "changed"
        return StepResult(
            name=self.name,
            status=status,
            detail=(
                f"HAProxy configured: SNI={self.reality_sni} -> "
                f"127.0.0.1:{self.haproxy_reality_backend_port}, "
                f"default -> 127.0.0.1:{self.caddy_internal_port}"
            ),
        )


# ---------------------------------------------------------------------------
# InstallCaddy
# ---------------------------------------------------------------------------


class InstallCaddy:
    """Install Caddy from official repo and deploy Meridian config.

    Replaces: roles/caddy/tasks/main.yml (install + config portions)

    Config strategy: Meridian writes to /etc/caddy/conf.d/meridian.caddy
    and ensures the main Caddyfile imports /etc/caddy/conf.d/*. The user's
    own Caddyfile is never overwritten.
    """

    name = "install_caddy"

    def __init__(
        self,
        domain: str,
        caddy_internal_port: int = 8443,
        ws_path: str = "",
        wss_internal_port: int = 0,
        panel_web_base_path: str = "",
        panel_internal_port: int = 2053,
        info_page_path: str = "",
        email: str = "",
        server_ip: str = "",
        skip_dns_check: bool = False,
    ) -> None:
        self.domain = domain
        self.caddy_internal_port = caddy_internal_port
        self.ws_path = ws_path
        self.wss_internal_port = wss_internal_port
        self.panel_web_base_path = panel_web_base_path
        self.panel_internal_port = panel_internal_port
        self.info_page_path = info_page_path
        self.email = email
        self.server_ip = server_ip
        self.skip_dns_check = skip_dns_check

    @_timed
    def run(self, conn: ServerConnection, ctx: dict[str, Any]) -> StepResult:
        # -- DNS pre-check --
        if not self.skip_dns_check:
            dns_result = _check_domain_dns(conn, self.domain, self.server_ip)
            if dns_result is not None:
                return StepResult(name=self.name, status="failed", detail=dns_result)

        # -- Install prerequisites --
        result = conn.run(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y "
            "debian-keyring debian-archive-keyring apt-transport-https curl dnsutils",
            timeout=120,
        )
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to install Caddy prerequisites: {result.stderr.strip()}",
            )

        # -- Add Caddy GPG key --
        result = conn.run(
            "curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key "
            "-o /etc/apt/keyrings/caddy-stable.asc && "
            "chmod 644 /etc/apt/keyrings/caddy-stable.asc",
            timeout=30,
        )
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to add Caddy GPG key: {result.stderr.strip()}",
            )

        # -- Add Caddy apt repository --
        repo_line = (
            "deb [signed-by=/etc/apt/keyrings/caddy-stable.asc] "
            "https://dl.cloudsmith.io/public/caddy/stable/deb/debian "
            "any-version main"
        )
        q_repo = shlex.quote(repo_line)
        result = conn.run(
            f"echo {q_repo} > /etc/apt/sources.list.d/caddy-stable.list",
            timeout=10,
        )
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to add Caddy repo: {result.stderr.strip()}",
            )

        # -- Install Caddy --
        result = conn.run(
            "DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y caddy",
            timeout=120,
        )
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to install Caddy: {result.stderr.strip()}",
            )

        # -- Create directories --
        conn.run(
            "mkdir -p /var/www/private /var/log/caddy /etc/caddy/conf.d && "
            "chown caddy:caddy /var/www/private /var/log/caddy /etc/caddy/conf.d",
            timeout=10,
        )

        # -- Deploy Meridian Caddy config --
        caddy_config = _render_caddy_config(
            domain=self.domain,
            caddy_internal_port=self.caddy_internal_port,
            ws_path=self.ws_path,
            wss_internal_port=self.wss_internal_port,
            panel_web_base_path=self.panel_web_base_path,
            panel_internal_port=self.panel_internal_port,
            info_page_path=self.info_page_path,
            email=self.email,
        )
        q_config = shlex.quote(caddy_config)
        result = conn.run(
            f"printf '%s' {q_config} > /etc/caddy/conf.d/meridian.caddy",
            timeout=10,
        )
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to write Caddy config: {result.stderr.strip()}",
            )

        # -- Ensure main Caddyfile imports conf.d --
        import_line = "import /etc/caddy/conf.d/*.caddy"
        q_import = shlex.quote(import_line)
        conn.run(
            f"grep -qxF {q_import} /etc/caddy/Caddyfile 2>/dev/null || echo {q_import} >> /etc/caddy/Caddyfile",
            timeout=10,
        )

        # -- Start/enable/reload Caddy --
        conn.run("systemctl enable caddy", timeout=10)
        result = conn.run("systemctl reload-or-restart caddy", timeout=15)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to start Caddy: {result.stderr.strip()}",
            )

        return StepResult(
            name=self.name,
            status="changed",
            detail=f"Caddy configured for {self.domain}:{self.caddy_internal_port}",
        )


# ---------------------------------------------------------------------------
# DeployConnectionPage
# ---------------------------------------------------------------------------


class DeployConnectionPage:
    """Deploy the connection info HTML page and stats infrastructure.

    Replaces: the connection page deployment portion of roles/caddy/tasks/main.yml

    Generates QR codes on the server using qrencode, deploys the stats update
    script with a cron job, and writes the connection-info HTML page.
    """

    name = "deploy_connection_page"

    def __init__(
        self,
        server_ip: str,
        domain: str,
        sni: str,
        reality_uuid: str,
        reality_public_key: str,
        reality_short_id: str,
        wss_uuid: str,
        ws_path: str,
        info_page_path: str,
        panel_internal_port: int = 2053,
        fingerprint: str = "chrome",
        xhttp_enabled: bool = True,
        xhttp_port: int = 0,
    ) -> None:
        self.server_ip = server_ip
        self.domain = domain
        self.sni = sni
        self.reality_uuid = reality_uuid
        self.reality_public_key = reality_public_key
        self.reality_short_id = reality_short_id
        self.wss_uuid = wss_uuid
        self.ws_path = ws_path
        self.info_page_path = info_page_path
        self.panel_internal_port = panel_internal_port
        self.fingerprint = fingerprint
        self.xhttp_enabled = xhttp_enabled
        self.xhttp_port = xhttp_port

    @_timed
    def run(self, conn: ServerConnection, ctx: dict[str, Any]) -> StepResult:
        # Install qrencode
        result = conn.run(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y qrencode",
            timeout=60,
        )
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to install qrencode: {result.stderr.strip()}",
            )

        # Build connection URLs
        reality_url = (
            f"vless://{self.reality_uuid}@{self.server_ip}:443"
            f"?encryption=none&flow=xtls-rprx-vision"
            f"&security=reality&sni={self.sni}&fp={self.fingerprint}"
            f"&pbk={self.reality_public_key}&sid={self.reality_short_id}"
            f"&type=tcp&headerType=none#VLESS-Reality"
        )

        wss_url = (
            f"vless://{self.wss_uuid}@{self.domain}:443"
            f"?encryption=none&security=tls&sni={self.domain}"
            f"&type=ws&host={self.domain}&path=%2F{self.ws_path}#VLESS-WSS-CDN"
        )

        # Generate QR codes as base64 PNG
        q_reality = shlex.quote(reality_url)
        result = conn.run(
            f"printf '%s' {q_reality} | qrencode -t PNG -o - -s 6 | base64 -w0",
            timeout=15,
        )
        reality_qr_b64 = result.stdout.strip() if result.returncode == 0 else ""

        q_wss = shlex.quote(wss_url)
        result = conn.run(
            f"printf '%s' {q_wss} | qrencode -t PNG -o - -s 6 | base64 -w0",
            timeout=15,
        )
        wss_qr_b64 = result.stdout.strip() if result.returncode == 0 else ""

        xhttp_qr_b64 = ""
        xhttp_url = ""
        if self.xhttp_enabled and self.xhttp_port > 0:
            xhttp_url = (
                f"vless://{self.reality_uuid}@{self.server_ip}:{self.xhttp_port}"
                f"?encryption=none&security=reality&sni={self.sni}&fp={self.fingerprint}"
                f"&pbk={self.reality_public_key}&sid={self.reality_short_id}"
                f"&type=xhttp&mode=packet-up&path=%2F#VLESS-XHTTP"
            )
            q_xhttp = shlex.quote(xhttp_url)
            result = conn.run(
                f"printf '%s' {q_xhttp} | qrencode -t PNG -o - -s 6 | base64 -w0",
                timeout=15,
            )
            xhttp_qr_b64 = result.stdout.strip() if result.returncode == 0 else ""

        # Store QR data in context for the HTML template
        ctx["reality_qr_b64"] = reality_qr_b64
        ctx["wss_qr_b64"] = wss_qr_b64
        ctx["xhttp_qr_b64"] = xhttp_qr_b64
        ctx["reality_url"] = reality_url
        ctx["wss_url"] = wss_url
        ctx["xhttp_url"] = xhttp_url

        # Deploy stats update script
        stats_script = _render_stats_script(self.panel_internal_port)
        q_script = shlex.quote(stats_script)
        conn.run("mkdir -p /etc/meridian", timeout=5)
        conn.run(f"printf '%s' {q_script} > /etc/meridian/update-stats.py", timeout=10)
        conn.run("chmod 700 /etc/meridian/update-stats.py", timeout=5)

        # Create stats directory
        conn.run(
            "mkdir -p /var/www/private/stats && chown caddy:caddy /var/www/private/stats",
            timeout=10,
        )

        # Run stats update once
        conn.run("python3 /etc/meridian/update-stats.py", timeout=15)

        # Add cron job (idempotent via crontab manipulation)
        cron_job = "*/5 * * * * python3 /etc/meridian/update-stats.py"
        q_cron = shlex.quote(cron_job)
        conn.run(
            f"(crontab -l 2>/dev/null | grep -v 'update-stats.py'; echo {q_cron}) | crontab -",
            timeout=10,
        )

        # NOTE: The actual connection-info.html.j2 template deployment is handled
        # separately because it requires the full Jinja2 template rendering pipeline
        # with the connection-info.html.j2 template. The caller should render the
        # template with the QR data from ctx and write it to /var/www/private/index.html.

        return StepResult(
            name=self.name,
            status="changed",
            detail=("Connection page infrastructure deployed (QR codes generated, stats cron enabled)"),
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_domain_dns(conn: ServerConnection, domain: str, server_ip: str) -> str | None:
    """Check if the domain resolves to the server IP.

    Returns an error message if DNS check fails, None if OK.
    """
    q_domain = shlex.quote(domain)
    result = conn.run(f"dig +short {q_domain} @8.8.8.8", timeout=10)
    resolved = result.stdout.strip() if result.returncode == 0 else ""

    if not resolved:
        # Empty DNS response -- might be a new domain, let it pass
        return None

    if resolved != server_ip:
        return (
            f"{domain} does not resolve to this server's IP ({server_ip}).\n"
            f"DNS returned: {resolved}\n\n"
            f"Caddy needs the domain to point DIRECTLY to this server for TLS certificates.\n\n"
            f"Fix: In Cloudflare, set the A record to 'DNS only' (grey cloud), then re-run.\n"
            f"After setup succeeds, switch to 'Proxied' (orange cloud).\n\n"
            f"To skip this check: use skip_dns_check=True"
        )

    return None
