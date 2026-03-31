"""nginx and connection page provisioning steps.

nginx handles both SNI-based TCP routing (stream module) and TLS termination
+ web serving (http module), replacing the previous HAProxy + Caddy setup.
Certificate management via acme.sh.
"""

from __future__ import annotations

import shlex
import textwrap

from meridian.config import DEFAULT_FINGERPRINT
from meridian.provision.steps import ProvisionContext, StepResult
from meridian.ssh import ServerConnection

# ---------------------------------------------------------------------------
# nginx stream configuration (SNI routing — replaces HAProxy)
# ---------------------------------------------------------------------------


def _render_nginx_stream_config(
    reality_sni: str,
    reality_backend_port: int,
    nginx_internal_port: int,
    server_ip: str = "",
    domain: str = "",
) -> str:
    """Render the nginx stream configuration for SNI-based routing.

    nginx stream sits on port 443 and inspects the TLS ClientHello SNI
    WITHOUT terminating TLS. Reality-targeted SNIs go to Xray, all other
    SNIs (server IP, domain, unknown) go to the nginx HTTPS backend.
    Unknown SNIs get the same response as direct IP access — no routing
    differential for censors to detect.
    """
    # Build SNI → backend map entries
    map_entries = [
        f"    {reality_sni}  xray_reality;",
    ]
    if server_ip:
        map_entries.append(f"    {server_ip}  nginx_https;")
    if domain:
        map_entries.append(f"    {domain}  nginx_https;")

    # No SNI (browsers connecting to bare IP per RFC 6066) → nginx
    map_entries.append('    ""  nginx_https;')
    # Unknown SNI → same response as direct IP (no routing differential)
    map_entries.append("    default  nginx_https;")

    map_block = "\n".join(map_entries)

    # Flow comment lines
    flow_lines = [
        f"SNI={reality_sni} -> Xray Reality (127.0.0.1:{reality_backend_port})",
    ]
    if server_ip:
        flow_lines.append(f"SNI={server_ip} -> nginx HTTPS (127.0.0.1:{nginx_internal_port})")
    if domain:
        flow_lines.append(f"SNI={domain} -> nginx HTTPS (127.0.0.1:{nginx_internal_port})")
    flow_lines.append(f"No SNI (bare IP) -> nginx HTTPS (127.0.0.1:{nginx_internal_port})")
    flow_lines.append("Unknown SNI -> nginx HTTPS (same as direct IP)")
    flow_comment = "\n".join(f"#   {line}" for line in flow_lines)

    return textwrap.dedent(f"""\
        # nginx SNI Router (stream module)
        # Managed by Meridian. Manual edits will be overwritten on next deploy.
        #
        # Flow:
        {flow_comment}

        map $ssl_preread_server_name $meridian_backend {{
        {map_block}
        }}

        upstream xray_reality {{
            server 127.0.0.1:{reality_backend_port};
        }}

        upstream nginx_https {{
            server 127.0.0.1:{nginx_internal_port};
        }}

        server {{
            listen 443;
            listen [::]:443;
            ssl_preread on;
            proxy_pass $meridian_backend;
            # Short timeout — don't wait 60s (default) if a backend is
            # temporarily unavailable.
            proxy_connect_timeout 1s;
        }}
    """)


# ---------------------------------------------------------------------------
# nginx http configuration (TLS + reverse proxy + web — replaces Caddy)
# ---------------------------------------------------------------------------


def _render_nginx_http_config(
    domain: str,
    nginx_internal_port: int,
    ws_path: str,
    wss_internal_port: int,
    panel_web_base_path: str,
    panel_internal_port: int,
    info_page_path: str,
    email: str = "",
    xhttp_path: str = "",
    xhttp_internal_port: int = 0,
) -> str:
    """Render the nginx http configuration for domain mode.

    Architecture: nginx stream (port 443) -> nginx http (internal port)
    nginx stream does SNI routing without TLS termination.
    nginx http handles TLS with certificates issued by acme.sh.
    """
    wss_block = textwrap.dedent(f"""\

        # --- VLESS+WSS Fallback (Cloudflare CDN path) ---
        location /{ws_path} {{
            proxy_pass http://127.0.0.1:{wss_internal_port};
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection $connection_upgrade;
            proxy_read_timeout 360s;
        }}
    """).rstrip()

    xhttp_block = ""
    if xhttp_path and xhttp_internal_port > 0:
        xhttp_block = textwrap.dedent(f"""\

            # --- VLESS+XHTTP (enhanced stealth, nginx-terminated TLS) ---
            location /{xhttp_path}/ {{
                proxy_pass http://127.0.0.1:{xhttp_internal_port};
                proxy_http_version 1.1;
                proxy_read_timeout 360s;
                proxy_buffering off;
            }}
        """).rstrip()

    # Default: realistic nginx — root 403 (directory listing forbidden),
    # unknown paths 404 (not found). Matches genuine nginx with empty docroot.
    # Three independent censor-perspective assessments confirmed 403/404 is
    # less fingerprintable than 444 (silent close after TLS), which virtually
    # no legitimate server does and rated 9/10 suspiciousness.
    root_action = "return 403;"
    default_action = "return 404;"

    return _render_nginx_server_block(
        host=domain,
        nginx_internal_port=nginx_internal_port,
        panel_web_base_path=panel_web_base_path,
        panel_internal_port=panel_internal_port,
        info_page_path=info_page_path,
        extra_locations=wss_block + xhttp_block,
        root_action=root_action,
        default_action=default_action,
        mode_comment="Domain Mode",
        tls_comment=(f"TLS: certificates issued by acme.sh for {domain}"),
        redirect_http=True,
    )


def _render_nginx_ip_config(
    server_ip: str,
    nginx_internal_port: int,
    panel_web_base_path: str,
    panel_internal_port: int,
    info_page_path: str,
    email: str = "",
    xhttp_path: str = "",
    xhttp_internal_port: int = 0,
) -> str:
    """Render nginx http configuration for IP certificate mode (no domain).

    Architecture: nginx stream (port 443) -> nginx http (internal port)
    TLS via Let's Encrypt IP certificate (acme.sh --certificate-profile shortlived).
    """
    xhttp_block = ""
    if xhttp_path and xhttp_internal_port > 0:
        xhttp_block = textwrap.dedent(f"""\

            # --- VLESS+XHTTP (enhanced stealth, nginx-terminated TLS) ---
            location /{xhttp_path}/ {{
                proxy_pass http://127.0.0.1:{xhttp_internal_port};
                proxy_http_version 1.1;
                proxy_read_timeout 360s;
                proxy_buffering off;
            }}
        """).rstrip()

    # Default: realistic nginx — root 403 (directory listing forbidden),
    # unknown paths 404 (not found). Matches genuine nginx with empty docroot.
    # See domain mode comment for rationale (blind censor assessment).
    root_action = "return 403;"
    default_action = "return 404;"

    return _render_nginx_server_block(
        host=server_ip,
        nginx_internal_port=nginx_internal_port,
        panel_web_base_path=panel_web_base_path,
        panel_internal_port=panel_internal_port,
        info_page_path=info_page_path,
        extra_locations=xhttp_block,
        root_action=root_action,
        default_action=default_action,
        mode_comment="IP Certificate Mode",
        tls_comment=("TLS: Let's Encrypt IP certificate (acme.sh, shortlived profile)"),
        redirect_http=False,
    )


def _render_nginx_server_block(
    host: str,
    nginx_internal_port: int,
    panel_web_base_path: str,
    panel_internal_port: int,
    info_page_path: str,
    extra_locations: str,
    root_action: str,
    default_action: str,
    mode_comment: str,
    tls_comment: str,
    redirect_http: bool = True,
) -> str:
    """Render the shared nginx server block structure.

    Used by both domain and IP config renderers to avoid duplication.
    redirect_http: True = HTTP→HTTPS redirect (domain mode, has real content).
                   False = ACME-only, no redirect (IP mode — redirect to
                   HTTPS that returns 403 is a contradiction signal).
    """
    csp = "default-src 'self'; img-src 'self' data:; connect-src 'self'"

    # Port 80 behavior: domain mode redirects (has real content),
    # IP mode serves ACME challenges only (no redirect — redirect to
    # HTTPS that returns 403 is a contradiction signal for censors).
    if redirect_http:
        http_default = "return 301 https://$host$request_uri;"
    else:
        http_default = "return 444;"

    return textwrap.dedent(f"""\
        # Meridian Proxy Configuration ({mode_comment})
        # Managed by Meridian — this file is overwritten on each deploy.
        #
        # Architecture: nginx stream (port 443) -> nginx http (port {nginx_internal_port})
        # {tls_comment}

        # --- Cache control for connection pages (map avoids add_header inheritance) ---
        map $uri $meridian_cache {{
            ~*/pwa/            "public, max-age=86400";
            ~*/config\\.json$   "no-cache, must-revalidate";
            ~*/sub\\.txt$       "no-cache, must-revalidate";
            ~*/stats/          "no-cache, must-revalidate";
            default            "no-store";
        }}

        map $uri $meridian_sw {{
            ~*/sw\\.js$   "/";
            default      "";
        }}

        # WebSocket upgrade: only set Connection: upgrade when client sends Upgrade header
        map $http_upgrade $connection_upgrade {{
            default upgrade;
            ""      close;
        }}

        server {{
            listen 127.0.0.1:{nginx_internal_port} ssl http2;
            server_name {host};
            server_tokens off;

            ssl_certificate     /etc/ssl/meridian/fullchain.pem;
            ssl_certificate_key /etc/ssl/meridian/key.pem;
            ssl_protocols TLSv1.2 TLSv1.3;
    {extra_locations}

            # --- 3x-ui Panel (management interface on secret path) ---
            location /{panel_web_base_path}/ {{
                proxy_pass http://127.0.0.1:{panel_internal_port};
            }}

            # --- Connection Info Pages (PWA with per-client config) ---
            # alias strips the location prefix (like Caddy's handle_path).
            location /{info_page_path}/ {{
                alias /var/www/private/;

                add_header Cache-Control $meridian_cache always;
                add_header Service-Worker-Allowed $meridian_sw always;
                add_header Content-Security-Policy "{csp}" always;
                add_header X-Content-Type-Options "nosniff" always;
                add_header X-Frame-Options "DENY" always;
                add_header Referrer-Policy "no-referrer" always;
            }}

            # Root: exact match (403 = directory listing forbidden, or 444 = drop)
            location = / {{
                {root_action}
            }}

            # Default: everything else (404 = not found, or 444 = drop)
            location / {{
                {default_action}
            }}

            access_log /var/log/nginx/meridian.log;
        }}

        # --- HTTP: ACME challenge{" + redirect" if redirect_http else " only (no redirect)"} ---
        server {{
            listen 80;
            listen [::]:80;
            server_name {host};
            server_tokens off;

            location /.well-known/acme-challenge/ {{
                root /var/www/acme;
            }}

            location / {{
                {http_default}
            }}
        }}
    """)


# ---------------------------------------------------------------------------
# Stats update script template
# ---------------------------------------------------------------------------


def _render_stats_script(panel_internal_port: int) -> str:
    """Render the stats update Python script."""
    return textwrap.dedent(f"""\
        #!/usr/bin/env python3
        \"\"\"Fetch per-client traffic stats from 3x-ui and write per-client JSON files.

        Each client gets a stats file named by their Reality UUID -- the same UUID
        that appears in their VLESS connection URL. Only someone with the URL can
        find their stats file. Runs via cron every 5 minutes.
        \"\"\"
        import json, urllib.request, urllib.parse, http.cookiejar, os, time, sys

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
            login_data = "username={{0}}&password={{1}}".format(
                urllib.parse.quote(creds.get('panel_username', ''), safe=''),
                urllib.parse.quote(creds.get('panel_password', ''), safe=''),
            ).encode()
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
# InstallNginx (replaces InstallHAProxy + InstallCaddy)
# ---------------------------------------------------------------------------


class InstallNginx:
    """Install nginx and deploy SNI routing + TLS + web serving configuration.

    Combines the previous InstallHAProxy (SNI routing) and InstallCaddy
    (TLS termination + web serving) into a single nginx process.

    nginx stream module handles SNI routing on port 443 (no TLS termination).
    nginx http module handles TLS + reverse proxy + static files on internal port.
    acme.sh handles certificate issuance and renewal.

    On upgrade from HAProxy+Caddy, stops and disables the old services.
    """

    name = "Install nginx"

    def __init__(
        self,
        domain: str,
        reality_sni: str | None = None,
        reality_backend_port: int | None = None,
        nginx_internal_port: int = 8443,
        ws_path: str | None = None,
        wss_internal_port: int | None = None,
        panel_web_base_path: str | None = None,
        panel_internal_port: int | None = None,
        info_page_path: str | None = None,
        email: str = "",
        server_ip: str | None = None,
        skip_dns_check: bool = False,
        ip_mode: bool = False,
        xhttp_path: str | None = None,
        xhttp_internal_port: int | None = None,
    ) -> None:
        self.domain = domain
        self.reality_sni = reality_sni
        self.reality_backend_port = reality_backend_port
        self.nginx_internal_port = nginx_internal_port
        self.ws_path = ws_path
        self.wss_internal_port = wss_internal_port
        self.panel_web_base_path = panel_web_base_path
        self.panel_internal_port = panel_internal_port
        self.info_page_path = info_page_path
        self.email = email
        self.server_ip = server_ip
        self.skip_dns_check = skip_dns_check
        self.ip_mode = ip_mode
        self.xhttp_path = xhttp_path
        self.xhttp_internal_port = xhttp_internal_port

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        # Resolve runtime values from context (populated by ConfigurePanel).
        # None = "not provided by caller, use context". Explicit values
        # (including falsy ones like 0 or "") are respected as-is.
        def _r(val, fallback):  # noqa: ANN001, ANN202
            return val if val is not None else fallback

        panel_web_base_path = _r(self.panel_web_base_path, ctx.get("web_base_path", ""))
        info_page_path = _r(self.info_page_path, ctx.get("info_page_path", ""))
        panel_internal_port = _r(self.panel_internal_port, ctx.panel_port)
        server_ip = _r(self.server_ip, ctx.ip)
        xhttp_path = _r(self.xhttp_path, ctx.get("xhttp_path", ""))
        xhttp_internal_port = _r(
            self.xhttp_internal_port,
            ctx.xhttp_port if ctx.xhttp_enabled else 0,
        )
        ws_path = _r(self.ws_path, ctx.get("ws_path", ""))
        wss_internal_port = _r(self.wss_internal_port, ctx.wss_port)
        reality_sni = _r(self.reality_sni, ctx.sni)
        reality_backend_port = _r(self.reality_backend_port, ctx.reality_port)

        # -- DNS pre-check (domain mode only) --
        if not self.ip_mode and not self.skip_dns_check:
            dns_result = _check_domain_dns(conn, self.domain, server_ip)
            if dns_result is not None:
                return StepResult(name=self.name, status="failed", detail=dns_result)

        # -- Upgrade path: stop old HAProxy and Caddy if present --
        conn.run(
            "systemctl stop haproxy 2>/dev/null; systemctl disable haproxy 2>/dev/null; true",
            timeout=10,
        )
        conn.run(
            "systemctl stop caddy 2>/dev/null; systemctl disable caddy 2>/dev/null; true",
            timeout=10,
        )
        # Remove old watchdog immediately to prevent it from restarting
        # haproxy/caddy during the deploy (cron runs every 5 min)
        conn.run("rm -f /etc/meridian/health-check.sh", timeout=5)
        # Clean up old config files and cert storage
        conn.run(
            "rm -f /etc/haproxy/haproxy.cfg /etc/caddy/conf.d/meridian.caddy /etc/caddy/Caddyfile && "
            "rm -rf /etc/systemd/system/haproxy.service.d /etc/systemd/system/caddy.service.d "
            "/var/lib/caddy/.local/share/caddy && "
            "systemctl daemon-reload 2>/dev/null; true",
            timeout=10,
        )

        # -- Check if nginx is already installed --
        check = conn.run("dpkg -l nginx 2>/dev/null | grep -q '^ii'", timeout=10)
        already_installed = check.returncode == 0

        if not already_installed:
            result = conn.run(
                "DEBIAN_FRONTEND=noninteractive apt-get install -y nginx",
                timeout=120,
            )
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"Failed to install nginx: {result.stderr.strip()}",
                )

        # -- Ensure stream module is available --
        # On Ubuntu/Debian, nginx compiles stream as a dynamic module
        # (--with-stream=dynamic). The .so file ships in libnginx-mod-stream,
        # which is NOT pulled in by the base nginx package. Install it
        # unconditionally (apt is idempotent) to cover both fresh installs
        # and upgrades from HAProxy+Caddy where it was never needed.
        conn.run(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq libnginx-mod-stream 2>/dev/null; true",
            timeout=60,
        )
        # Verify the module .so exists (compile flags ≠ runtime availability)
        check = conn.run(
            "test -f /usr/lib/nginx/modules/ngx_stream_module.so || nginx -V 2>&1 | grep -q 'with-stream '",
            timeout=10,
        )
        if check.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail="nginx stream module not available — install libnginx-mod-stream",
            )

        # -- Create directories --
        conn.run(
            "mkdir -p /var/www/private /var/www/acme/.well-known/acme-challenge "
            "/etc/ssl/meridian /etc/nginx/stream.d && "
            "chown -R www-data:www-data /var/www/private /var/www/acme",
            timeout=10,
        )

        # -- Ensure webmanifest MIME type is registered --
        # nginx doesn't know .webmanifest by default; PWA manifests need it.
        conn.run(
            "grep -q webmanifest /etc/nginx/mime.types || "
            r"sed -i '/^}/i \    application/manifest+json  webmanifest;' /etc/nginx/mime.types",
            timeout=10,
        )

        # -- Install acme.sh (if not already installed) --
        check = conn.run("test -f /root/.acme.sh/acme.sh", timeout=5)
        if check.returncode != 0:
            # email='' breaks acme.sh installer (shift error), omit when empty
            email_flag = f"email={shlex.quote(self.email)}" if self.email else ""
            result = conn.run(
                f"curl -fsSL https://get.acme.sh | sh -s -- {email_flag}",
                timeout=60,
            )
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"Failed to install acme.sh: {result.stderr.strip()}",
                )

        # -- Bootstrap: generate self-signed cert so nginx can start --
        check = conn.run("test -f /etc/ssl/meridian/fullchain.pem", timeout=5)
        if check.returncode != 0:
            cert_host = server_ip if self.ip_mode else self.domain
            q_subj = shlex.quote(f"/CN={cert_host}")
            result = conn.run(
                f"openssl req -x509 -newkey rsa:2048 -keyout /etc/ssl/meridian/key.pem "
                f"-out /etc/ssl/meridian/fullchain.pem -days 1 -nodes "
                f"-subj {q_subj}",
                timeout=15,
            )
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail="Failed to generate bootstrap certificate",
                )

        # -- Deploy nginx stream config --
        stream_config = _render_nginx_stream_config(
            reality_sni=reality_sni,
            reality_backend_port=reality_backend_port,
            nginx_internal_port=self.nginx_internal_port,
            server_ip=server_ip,
            domain=self.domain,
        )
        q_stream = shlex.quote(stream_config)
        result = conn.run(
            f"printf '%s' {q_stream} > /etc/nginx/stream.d/meridian.conf",
            timeout=10,
        )
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to write stream config: {result.stderr.strip()}",
            )

        # -- Deploy nginx http config --
        if self.ip_mode:
            http_config = _render_nginx_ip_config(
                server_ip=server_ip,
                nginx_internal_port=self.nginx_internal_port,
                panel_web_base_path=panel_web_base_path,
                panel_internal_port=panel_internal_port,
                info_page_path=info_page_path,
                email=self.email,
                xhttp_path=xhttp_path,
                xhttp_internal_port=xhttp_internal_port,
            )
        else:
            http_config = _render_nginx_http_config(
                domain=self.domain,
                nginx_internal_port=self.nginx_internal_port,
                ws_path=ws_path,
                wss_internal_port=wss_internal_port,
                panel_web_base_path=panel_web_base_path,
                panel_internal_port=panel_internal_port,
                info_page_path=info_page_path,
                email=self.email,
                xhttp_path=xhttp_path,
                xhttp_internal_port=xhttp_internal_port,
            )
        q_http = shlex.quote(http_config)
        result = conn.run(
            f"printf '%s' {q_http} > /etc/nginx/conf.d/meridian-http.conf",
            timeout=10,
        )
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to write http config: {result.stderr.strip()}",
            )

        # -- Ensure nginx.conf has a stream block --
        # The default nginx.conf only has an http{} block with
        # include conf.d/*.conf. We need a top-level stream{} block
        # for SNI routing. Stream config lives in stream.d/ to avoid
        # being included inside http{} by the default conf.d/*.conf glob.
        check = conn.run("grep -q 'stream {' /etc/nginx/nginx.conf", timeout=5)
        if check.returncode != 0:
            # Append stream block at the end of nginx.conf (outside http{})
            stream_block = "\\nstream {\\n    include /etc/nginx/stream.d/*.conf;\\n}\\n"
            conn.run(
                f"printf '{stream_block}' >> /etc/nginx/nginx.conf",
                timeout=10,
            )

        # -- Remove default site (conflicts with our port 80 listener) --
        conn.run("rm -f /etc/nginx/sites-enabled/default", timeout=5)

        # -- Validate configuration --
        result = conn.run("nginx -t 2>&1", timeout=10)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"nginx config validation failed: {result.stderr.strip() or result.stdout.strip()}",
            )

        # -- Ensure nginx restarts on failure --
        conn.run(
            "mkdir -p /etc/systemd/system/nginx.service.d && "
            "printf '[Service]\\nRestart=on-failure\\nRestartSec=5\\n' "
            "> /etc/systemd/system/nginx.service.d/restart.conf && "
            "systemctl daemon-reload",
            timeout=10,
        )

        # -- Start/enable/reload nginx --
        conn.run("systemctl enable nginx", timeout=10)
        result = conn.run("systemctl reload-or-restart nginx", timeout=15)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to start nginx: {result.stderr.strip()}",
            )

        # -- Issue real TLS certificate via acme.sh --
        cert_host = server_ip if self.ip_mode else self.domain
        q_cert_host = shlex.quote(cert_host)
        profile_flag = " --certificate-profile shortlived" if self.ip_mode else ""

        result = conn.run(
            f"/root/.acme.sh/acme.sh --issue -d {q_cert_host} "
            f"--webroot /var/www/acme --server letsencrypt{profile_flag} 2>&1",
            timeout=120,
        )
        # acme.sh returns 0 on success, 2 if cert already valid (skip renewal)
        cert_issued = result.returncode in (0, 2)

        if cert_issued:
            # Install cert and set reload command for auto-renewal
            conn.run(
                f"/root/.acme.sh/acme.sh --install-cert -d {q_cert_host} "
                f"--key-file /etc/ssl/meridian/key.pem "
                f"--fullchain-file /etc/ssl/meridian/fullchain.pem "
                f'--reloadcmd "systemctl reload nginx" 2>&1',
                timeout=30,
            )
            # Reload to pick up the real cert
            conn.run("systemctl reload nginx", timeout=10)

        host = server_ip if self.ip_mode else self.domain
        if cert_issued:
            cert_note = "TLS cert issued"
        else:
            # ACME failed — server runs with self-signed cert.
            # Reality VPN works regardless (own encryption), but connection
            # pages will show browser cert warnings until resolved.
            cert_note = (
                "WARNING: TLS cert failed — using self-signed. "
                "Connection pages will show cert warnings. "
                "Check port 80 is open and domain resolves correctly"
            )
        return StepResult(
            name=self.name,
            status="changed",
            detail=f"nginx configured for {host}:{self.nginx_internal_port} ({cert_note})",
        )


# ---------------------------------------------------------------------------
# DeployPWAAssets
# ---------------------------------------------------------------------------


class DeployPWAAssets:
    """Deploy shared PWA static assets to /var/www/private/pwa/.

    These assets (JS, CSS, service worker, icon) are identical for all
    clients and deployed once.  Per-client files (config.json, manifest,
    index.html, sub.txt) are deployed by DeployConnectionPage.
    """

    name = "Deploy PWA assets"

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        from meridian.pwa import upload_pwa_assets

        try:
            ok = upload_pwa_assets(conn)
        except Exception as exc:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to load PWA assets: {exc}",
            )
        if not ok:
            return StepResult(
                name=self.name,
                status="failed",
                detail="Failed to upload shared PWA assets",
            )
        return StepResult(
            name=self.name,
            status="changed",
            detail="Shared PWA assets deployed to /var/www/private/pwa/",
        )


# ---------------------------------------------------------------------------
# DeployConnectionPage
# ---------------------------------------------------------------------------


class DeployConnectionPage:
    """Deploy the connection info HTML page and stats infrastructure.

    Generates QR codes on the server using qrencode, deploys the stats update
    script with a cron job, and renders+uploads the connection-info HTML page
    for the default client.

    Reads credentials and config from ProvisionContext (populated by
    ConfigurePanel and earlier steps).
    """

    name = "Deploy connection page"

    def __init__(
        self,
        server_ip: str,
        fingerprint: str = DEFAULT_FINGERPRINT,
    ) -> None:
        self.server_ip = server_ip
        self.fingerprint = fingerprint

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        # Read credentials from context (populated by ConfigurePanel)
        creds = ctx["credentials"]
        sni = creds.server.sni or ctx.sni
        domain = creds.server.domain or ctx.domain
        reality_uuid = creds.reality.uuid or ""
        reality_public_key = creds.reality.public_key or ""
        reality_short_id = creds.reality.short_id or ""
        wss_uuid = creds.wss.uuid or ""
        ws_path = creds.wss.ws_path or ""
        info_page_path = creds.panel.info_page_path or ctx.get("info_page_path", "")
        panel_internal_port = creds.panel.port or ctx.panel_port
        first_client_name = ctx.get("first_client_name", "default") or "default"
        xhttp_enabled = ctx.xhttp_enabled
        xhttp_path = creds.xhttp.xhttp_path or ctx.get("xhttp_path", "")

        if not reality_uuid:
            return StepResult(
                name=self.name,
                status="failed",
                detail="No Reality UUID found — ConfigurePanel may have failed",
            )

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
            f"vless://{reality_uuid}@{self.server_ip}:443"
            f"?encryption=none&flow=xtls-rprx-vision"
            f"&security=reality&sni={sni}&fp={self.fingerprint}"
            f"&pbk={reality_public_key}&sid={reality_short_id}"
            f"&type=tcp&headerType=none#VLESS-Reality"
        )

        wss_url = ""
        if domain and wss_uuid and ws_path:
            wss_url = (
                f"vless://{wss_uuid}@{domain}:443"
                f"?encryption=none&security=tls&sni={domain}"
                f"&type=ws&host={domain}&path=%2F{ws_path}#VLESS-WSS-CDN"
            )

        # Generate QR codes as base64 PNG
        q_reality = shlex.quote(reality_url)
        result = conn.run(
            f"printf '%s' {q_reality} | qrencode -t PNG -o - -s 6 | base64 | tr -d '\\n'",
            timeout=15,
        )
        reality_qr_b64 = result.stdout.strip() if result.returncode == 0 else ""

        wss_qr_b64 = ""
        if wss_url:
            q_wss = shlex.quote(wss_url)
            result = conn.run(
                f"printf '%s' {q_wss} | qrencode -t PNG -o - -s 6 | base64 | tr -d '\\n'",
                timeout=15,
            )
            wss_qr_b64 = result.stdout.strip() if result.returncode == 0 else ""

        xhttp_qr_b64 = ""
        xhttp_url = ""
        if xhttp_enabled and xhttp_path:
            # Use domain if available, otherwise IP
            xhttp_host = domain or self.server_ip
            xhttp_url = (
                f"vless://{reality_uuid}@{xhttp_host}:443"
                f"?encryption=none&security=tls"
                f"&type=xhttp&path=%2F{xhttp_path}#VLESS-XHTTP"
            )
            q_xhttp = shlex.quote(xhttp_url)
            result = conn.run(
                f"printf '%s' {q_xhttp} | qrencode -t PNG -o - -s 6 | base64 | tr -d '\\n'",
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
        stats_script = _render_stats_script(panel_internal_port)
        q_script = shlex.quote(stats_script)
        conn.run("mkdir -p /etc/meridian", timeout=5)
        conn.run(f"printf '%s' {q_script} > /etc/meridian/update-stats.py", timeout=10)
        conn.run("chmod 700 /etc/meridian/update-stats.py", timeout=5)

        # Create stats directory
        conn.run(
            "mkdir -p /var/www/private/stats && chown www-data:www-data /var/www/private/stats",
            timeout=10,
        )

        # Run stats update once
        conn.run("python3 /etc/meridian/update-stats.py", timeout=15)

        # Add cron job (idempotent via crontab manipulation), with syslog logging
        cron_job = "*/5 * * * * python3 /etc/meridian/update-stats.py 2>&1 | logger -t meridian-stats"
        q_cron = shlex.quote(cron_job)
        conn.run(
            f"(crontab -l 2>/dev/null | grep -v 'update-stats.py'; echo {q_cron}) | crontab -",
            timeout=10,
        )

        # Deploy health watchdog cron (checks Xray and nginx every 5 min)
        watchdog_script = (
            "#!/bin/sh\n"
            "# Meridian service health watchdog — restarts crashed services\n"
            "docker exec 3x-ui pgrep -f xray >/dev/null 2>&1 || "
            '{ logger -t meridian-health "Xray not running, restarting 3x-ui"; '
            "docker restart 3x-ui; }\n"
            "systemctl is-active --quiet nginx || "
            '{ logger -t meridian-health "nginx not running, restarting"; '
            "systemctl restart nginx; }\n"
        )
        q_watchdog = shlex.quote(watchdog_script)
        conn.run(f"printf '%s' {q_watchdog} > /etc/meridian/health-check.sh", timeout=10)
        conn.run("chmod 700 /etc/meridian/health-check.sh", timeout=5)

        watchdog_cron = "*/5 * * * * /etc/meridian/health-check.sh 2>&1 | logger -t meridian-health"
        q_wc = shlex.quote(watchdog_cron)
        conn.run(
            f"(crontab -l 2>/dev/null | grep -v 'health-check.sh'; echo {q_wc}) | crontab -",
            timeout=10,
        )

        # Build ProtocolURL list with QR data for connection page
        from meridian.models import ProtocolURL as _PU

        page_urls: list[_PU] = [_PU(key="reality", label="Primary", url=reality_url, qr_b64=reality_qr_b64)]
        if xhttp_url:
            page_urls.append(_PU(key="xhttp", label="XHTTP", url=xhttp_url, qr_b64=xhttp_qr_b64))
        if wss_url:
            page_urls.append(_PU(key="wss", label="CDN Backup", url=wss_url, qr_b64=wss_qr_b64))

        # Generate and upload PWA per-client files
        from meridian.pwa import generate_client_files, upload_client_files

        client_files = generate_client_files(
            page_urls,
            server_ip=self.server_ip,
            domain=domain,
            client_name=first_client_name,
            server_name=creds.branding.server_name,
            server_icon=creds.branding.icon,
            color=creds.branding.color,
        )

        if not upload_client_files(conn, reality_uuid, client_files):
            return StepResult(
                name=self.name,
                status="failed",
                detail="Stats deployed but PWA file upload failed",
            )

        page_url = f"https://{self.server_ip}/{info_page_path}/{reality_uuid}/"
        ctx["hosted_page_url"] = page_url

        return StepResult(
            name=self.name,
            status="changed",
            detail=f"Connection page live at {page_url}",
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
            f"The domain must point DIRECTLY to this server for TLS certificates.\n\n"
            f"Fix: In Cloudflare, set the A record to 'DNS only' (grey cloud), then re-run.\n"
            f"After setup succeeds, switch to 'Proxied' (orange cloud).\n\n"
            f"To skip this check: use skip_dns_check=True"
        )

    return None
