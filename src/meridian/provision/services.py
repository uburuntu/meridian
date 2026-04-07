"""nginx and connection page provisioning steps.

nginx handles both SNI-based TCP routing (stream module) and TLS termination
+ web serving (http module), replacing the previous HAProxy + Caddy setup.
Certificate management via acme.sh.
"""

from __future__ import annotations

import re
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
    WITHOUT terminating TLS. Reality-targeted SNIs go to Xray, server
    IP/domain/no-SNI go to nginx HTTPS (connection pages).
    Unknown SNIs are TCP-proxied to the Reality dest site — a censor
    probing with SNI=google.com sees the dest site's real cert, not
    nginx's, eliminating the SNI routing differential.
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
    # (needed for connection pages accessed via https://<IP>/...)
    map_entries.append('    ""  nginx_https;')
    # Unknown SNI → proxy to Reality dest (eliminates SNI differential —
    # censor probing with random SNIs sees the dest site, not nginx)
    map_entries.append("    default  reality_dest;")

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
    flow_lines.append(f"Unknown SNI -> TCP proxy to {reality_sni}:443 (no differential)")
    flow_comment = "\n".join(f"#   {line}" for line in flow_lines)

    return textwrap.dedent(f"""\
        # nginx SNI Router (stream module)
        # Managed by Meridian. Manual edits will be overwritten on next deploy.
        #
        # Flow:
        {flow_comment}

        map_hash_bucket_size 128;

        map $ssl_preread_server_name $meridian_backend {{
        {map_block}
        }}

        upstream xray_reality {{
            server 127.0.0.1:{reality_backend_port};
        }}

        upstream nginx_https {{
            server 127.0.0.1:{nginx_internal_port};
        }}

        upstream reality_dest {{
            server {reality_sni}:443;
        }}

        server {{
            listen 443;
            listen [::]:443;
            ssl_preread on;
            proxy_pass $meridian_backend;
            # Short timeout — don't wait 60s (default) if a backend is
            # temporarily unavailable.
            proxy_connect_timeout 1s;
            # VPN sessions can idle for extended periods (user not browsing).
            # Default 10m kills these; 30m is more forgiving while still
            # reclaiming truly dead connections.
            proxy_timeout 30m;
            # TCP keepalives prevent NATs/firewalls from dropping idle
            # connections — critical for relay→exit paths.
            proxy_socket_keepalive on;
        }}
    """)


# ---------------------------------------------------------------------------
# nginx http configuration (TLS + reverse proxy + web — replaces Caddy)
# ---------------------------------------------------------------------------


def _render_xhttp_location(xhttp_path: str) -> str:
    """Render the XHTTP reverse proxy location block."""
    return textwrap.dedent(f"""\

        # --- VLESS+XHTTP (enhanced stealth, nginx-terminated TLS) ---
        # Long timeouts: XHTTP mode=auto lets clients negotiate streaming
        # modes (stream-one/stream-up) with long-lived connections.
        location /{xhttp_path}/ {{
            proxy_pass http://meridian_xhttp;
            proxy_http_version 1.1;
            # Empty Connection header enables upstream keepalive reuse —
            # without this, nginx sends Connection: close per request.
            proxy_set_header Connection "";
            proxy_read_timeout 86400s;
            proxy_send_timeout 86400s;
            proxy_buffering off;
            proxy_request_buffering off;
        }}
    """).rstrip()


def _render_xhttp_upstream(xhttp_internal_port: int) -> str:
    """Render the XHTTP upstream keepalive pool block."""
    return textwrap.dedent(f"""\
        upstream meridian_xhttp {{
            server 127.0.0.1:{xhttp_internal_port};
            keepalive 32;
            keepalive_requests 10000;
            keepalive_timeout 300s;
        }}
    """)


def _render_nginx_http_config(
    domain: str,
    nginx_internal_port: int,
    ws_path: str,
    wss_internal_port: int,
    panel_web_base_path: str,
    panel_internal_port: int,
    info_page_path: str,
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
    xhttp_upstream = ""
    if xhttp_path and xhttp_internal_port > 0:
        xhttp_block = _render_xhttp_location(xhttp_path)
        xhttp_upstream = _render_xhttp_upstream(xhttp_internal_port)

    # Root: nginx's built-in 403 page. NOT a custom Meridian page — custom
    # HTML would be fingerprintable (one known server reveals all others).
    # nginx generates 403/404 bodies itself, identical across all installs.
    root_action = "return 403;"
    default_action = "return 404;"

    return _render_nginx_server_block(
        host=domain,
        nginx_internal_port=nginx_internal_port,
        panel_web_base_path=panel_web_base_path,
        panel_internal_port=panel_internal_port,
        info_page_path=info_page_path,
        extra_locations=wss_block + xhttp_block,
        upstream_blocks=xhttp_upstream,
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
    xhttp_path: str = "",
    xhttp_internal_port: int = 0,
) -> str:
    """Render nginx http configuration for IP certificate mode (no domain).

    Architecture: nginx stream (port 443) -> nginx http (internal port)
    TLS via Let's Encrypt IP certificate (acme.sh --certificate-profile shortlived).
    """
    xhttp_block = ""
    xhttp_upstream = ""
    if xhttp_path and xhttp_internal_port > 0:
        xhttp_block = _render_xhttp_location(xhttp_path)
        xhttp_upstream = _render_xhttp_upstream(xhttp_internal_port)

    # Root: nginx's built-in 403 — see domain mode comment for rationale.
    root_action = "return 403;"
    default_action = "return 404;"

    return _render_nginx_server_block(
        host=server_ip,
        nginx_internal_port=nginx_internal_port,
        panel_web_base_path=panel_web_base_path,
        panel_internal_port=panel_internal_port,
        info_page_path=info_page_path,
        extra_locations=xhttp_block,
        upstream_blocks=xhttp_upstream,
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
    upstream_blocks: str = "",
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
    {upstream_blocks}
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

            # Root: nginx-generated 403 (not custom HTML — avoids fingerprinting)
            location = / {{
                {root_action}
            }}

            # Default: nginx-generated 404
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
# InstallNginx — install nginx binary, stream module, and acme.sh
# ---------------------------------------------------------------------------


class InstallNginx:
    """Install nginx, stream module, and acme.sh.

    Handles upgrade path from old HAProxy+Caddy stack, version
    requirements (>=1.16), and the nginx.org official repo fallback.
    """

    name = "Install nginx"

    def __init__(self, email: str = "") -> None:
        self.email = email

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        changed = False

        # -- Upgrade path: stop old HAProxy and Caddy if present --
        conn.run(
            "systemctl stop haproxy 2>/dev/null; systemctl disable haproxy 2>/dev/null; true",
            timeout=15,
        )
        conn.run(
            "systemctl stop caddy 2>/dev/null; systemctl disable caddy 2>/dev/null; true",
            timeout=15,
        )
        # Remove old watchdog immediately to prevent it from restarting
        # haproxy/caddy during the deploy (cron runs every 5 min)
        conn.run("rm -f /etc/meridian/health-check.sh", timeout=15)
        # Clean up old config files and cert storage
        conn.run(
            "rm -f /etc/haproxy/haproxy.cfg /etc/caddy/conf.d/meridian.caddy /etc/caddy/Caddyfile && "
            "rm -rf /etc/systemd/system/haproxy.service.d /etc/systemd/system/caddy.service.d "
            "/var/lib/caddy/.local/share/caddy && "
            "systemctl daemon-reload 2>/dev/null; true",
            timeout=15,
        )

        # -- Check if nginx is already installed and meets version requirement --
        check = conn.run("dpkg -l nginx 2>/dev/null | grep -q '^ii'", timeout=15)
        already_installed = check.returncode == 0
        needs_official_repo = False

        if already_installed:
            ver_check = conn.run("nginx -v 2>&1", timeout=15)
            ver_output = ver_check.stdout + ver_check.stderr
            m = re.search(r"nginx/(\d+)\.(\d+)", ver_output)
            if m and (int(m.group(1)), int(m.group(2))) < (1, 16):
                needs_official_repo = True
        else:
            # Not installed — try distro repo first, upgrade if too old
            result = conn.run(
                "DEBIAN_FRONTEND=noninteractive apt-get install -y nginx",
                timeout=180,
            )
            if result.returncode != 0:
                # Distro install failed — fall through to official repo
                needs_official_repo = True
            else:
                changed = True
                ver_check = conn.run("nginx -v 2>&1", timeout=15)
                ver_output = ver_check.stdout + ver_check.stderr
                m = re.search(r"nginx/(\d+)\.(\d+)", ver_output)
                if m and (int(m.group(1)), int(m.group(2))) < (1, 16):
                    needs_official_repo = True

        if needs_official_repo:
            # Install from official nginx.org repo (mirrors Docker pattern)
            distro = conn.run("bash -c '. /etc/os-release && echo $ID'", timeout=15)
            distro_name = distro.stdout.strip().lower() if distro.returncode == 0 else "ubuntu"

            codename = conn.run("bash -c '. /etc/os-release && echo $VERSION_CODENAME'", timeout=15)
            distro_codename = codename.stdout.strip() if codename.returncode == 0 else "jammy"

            # Remove conflicting distro packages before official repo install
            conn.run(
                "DEBIAN_FRONTEND=noninteractive apt-get remove -y"
                " nginx-common nginx-core nginx-full 'libnginx-mod-*' 2>/dev/null; true",
                timeout=120,
            )

            # Ensure keyrings directory exists (missing on Ubuntu < 22.04)
            conn.run("mkdir -p /etc/apt/keyrings && chmod 755 /etc/apt/keyrings", timeout=15)

            # Add nginx.org signing key
            result = conn.run(
                "curl -fsSL https://nginx.org/keys/nginx_signing.key"
                " -o /etc/apt/keyrings/nginx.asc"
                " && chmod 644 /etc/apt/keyrings/nginx.asc",
                timeout=60,
            )
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"Failed to add nginx signing key: {result.stderr.strip()[:200]}",
                )

            # Add nginx.org stable repo
            repo_line = (
                f"deb [signed-by=/etc/apt/keyrings/nginx.asc] "
                f"https://nginx.org/packages/{distro_name} "
                f"{distro_codename} nginx"
            )
            conn.run(
                f"echo {shlex.quote(repo_line)} > /etc/apt/sources.list.d/nginx-official.list",
                timeout=15,
            )

            # Pin official nginx packages higher to override distro
            conn.run(
                "printf 'Package: nginx*\\nPin: origin nginx.org\\n"
                "Pin-Priority: 900\\n' > /etc/apt/preferences.d/99nginx",
                timeout=15,
            )

            result = conn.run(
                "DEBIAN_FRONTEND=noninteractive apt-get update -qq"
                " && DEBIAN_FRONTEND=noninteractive apt-get install -y nginx",
                timeout=180,
            )
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"Failed to install nginx from official repo: {result.stderr.strip()[:200]}",
                )

            changed = True

            # Clean up stale load_module directives — official nginx has
            # stream compiled statically, old distro nginx.conf may reference
            # dynamic .so files that no longer exist.
            conn.run(
                "sed -i '/load_module.*ngx_stream_module/d' /etc/nginx/nginx.conf 2>/dev/null; true",
                timeout=15,
            )

        # -- Ensure stream module is available --
        conn.run(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq libnginx-mod-stream 2>/dev/null; true",
            timeout=120,
        )
        check = conn.run(
            "test -f /usr/lib/nginx/modules/ngx_stream_module.so || nginx -V 2>&1 | grep -q 'with-stream '",
            timeout=15,
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
            timeout=15,
        )

        # -- Ensure webmanifest MIME type is registered --
        conn.run(
            "grep -q webmanifest /etc/nginx/mime.types || "
            r"sed -i '/^}/i \    application/manifest+json  webmanifest;' /etc/nginx/mime.types",
            timeout=15,
        )

        # -- Install acme.sh (if not already installed) --
        check = conn.run("test -f /root/.acme.sh/acme.sh", timeout=15)
        if check.returncode != 0:
            # email='' breaks acme.sh installer (shift error), omit when empty
            email_flag = f"email={shlex.quote(self.email)}" if self.email else ""
            result = conn.run(
                f"curl -fsSL https://get.acme.sh | sh -s -- {email_flag}",
                timeout=120,
            )
            if result.returncode != 0:
                return StepResult(
                    name=self.name,
                    status="failed",
                    detail=f"Failed to install acme.sh: {result.stderr.strip()}",
                )
            changed = True

        return StepResult(name=self.name, status="changed" if changed else "ok")


# ---------------------------------------------------------------------------
# ConfigureNginx — deploy configs, validate, start/reload
# ---------------------------------------------------------------------------


def _resolve_ctx(val: object, fallback: object) -> object:
    """Resolve a constructor value with context fallback.

    None = "not provided by caller, use context". Explicit values
    (including falsy ones like 0 or "") are respected as-is.
    """
    return val if val is not None else fallback


class ConfigureNginx:
    """Deploy nginx stream + http configs, validate, and start/reload.

    Reads context values set by ConfigurePanel for paths and ports.
    """

    name = "Configure nginx"

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
        self.server_ip = server_ip
        self.skip_dns_check = skip_dns_check
        self.ip_mode = ip_mode
        self.xhttp_path = xhttp_path
        self.xhttp_internal_port = xhttp_internal_port

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        # Resolve runtime values from context (populated by ConfigurePanel).
        panel_web_base_path = _resolve_ctx(self.panel_web_base_path, ctx.get("web_base_path", ""))
        info_page_path = _resolve_ctx(self.info_page_path, ctx.get("info_page_path", ""))
        panel_internal_port = _resolve_ctx(self.panel_internal_port, ctx.panel_port)
        server_ip = _resolve_ctx(self.server_ip, ctx.ip)
        xhttp_path = _resolve_ctx(self.xhttp_path, ctx.get("xhttp_path", ""))
        xhttp_internal_port = _resolve_ctx(
            self.xhttp_internal_port,
            ctx.xhttp_port if ctx.xhttp_enabled else 0,
        )
        ws_path = _resolve_ctx(self.ws_path, ctx.get("ws_path", ""))
        wss_internal_port = _resolve_ctx(self.wss_internal_port, ctx.wss_port)
        reality_sni = _resolve_ctx(self.reality_sni, ctx.sni)
        reality_backend_port = _resolve_ctx(self.reality_backend_port, ctx.reality_port)

        # -- DNS pre-check (domain mode only) --
        if not self.ip_mode and not self.skip_dns_check:
            dns_result = _check_domain_dns(conn, self.domain, server_ip)
            if dns_result is not None:
                return StepResult(name=self.name, status="failed", detail=dns_result)

        # -- Bootstrap: generate self-signed cert so nginx can start --
        check = conn.run("test -f /etc/ssl/meridian/fullchain.pem", timeout=15)
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
            timeout=15,
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
                xhttp_path=xhttp_path,
                xhttp_internal_port=xhttp_internal_port,
            )
        q_http = shlex.quote(http_config)
        result = conn.run(
            f"printf '%s' {q_http} > /etc/nginx/conf.d/meridian-http.conf",
            timeout=15,
        )
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to write http config: {result.stderr.strip()}",
            )

        # -- Ensure nginx.conf has a stream block --
        check = conn.run("grep -q 'stream {' /etc/nginx/nginx.conf", timeout=15)
        if check.returncode != 0:
            stream_block = "\\nstream {\\n    include /etc/nginx/stream.d/*.conf;\\n}\\n"
            conn.run(
                f"printf '{stream_block}' >> /etc/nginx/nginx.conf",
                timeout=15,
            )

        # -- Remove default site (conflicts with our port 80 listener) --
        conn.run("rm -f /etc/nginx/sites-enabled/default", timeout=15)

        # -- Validate configuration --
        result = conn.run("nginx -t 2>&1", timeout=15)
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
            timeout=15,
        )

        # -- Start/enable/reload nginx --
        conn.run("systemctl enable nginx", timeout=15)
        result = conn.run("systemctl reload-or-restart nginx", timeout=30)
        if result.returncode != 0:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to start nginx: {result.stderr.strip()}",
            )

        host = server_ip if self.ip_mode else self.domain
        return StepResult(
            name=self.name,
            status="changed",
            detail=f"nginx configured for {host}:{self.nginx_internal_port}",
        )


# ---------------------------------------------------------------------------
# IssueTLSCert — issue real TLS certificate via acme.sh
# ---------------------------------------------------------------------------


class IssueTLSCert:
    """Issue a real TLS certificate via acme.sh and install it.

    Uses the webroot method against the running nginx. On failure, nginx
    continues running with a self-signed bootstrap cert — Reality VPN
    works regardless since it uses its own encryption.
    """

    name = "Issue TLS certificate"

    def __init__(
        self,
        domain: str,
        ip_mode: bool = False,
        server_ip: str | None = None,
    ) -> None:
        self.domain = domain
        self.ip_mode = ip_mode
        self.server_ip = server_ip

    def run(self, conn: ServerConnection, ctx: ProvisionContext) -> StepResult:
        server_ip = _resolve_ctx(self.server_ip, ctx.ip)
        cert_host = server_ip if self.ip_mode else self.domain
        q_cert_host = shlex.quote(cert_host)
        profile_flag = " --certificate-profile shortlived" if self.ip_mode else ""

        result = conn.run(
            f"/root/.acme.sh/acme.sh --issue -d {q_cert_host} "
            f"--webroot /var/www/acme --server letsencrypt{profile_flag} 2>&1",
            timeout=180,
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
                timeout=60,
            )
            # Reload to pick up the real cert
            conn.run("systemctl reload nginx", timeout=15)

        if cert_issued:
            return StepResult(
                name=self.name,
                status="changed",
                detail=f"TLS cert issued for {cert_host}",
            )

        # ACME failed — server runs with self-signed cert.
        # Reality VPN works regardless (own encryption), but connection
        # pages will show browser cert warnings until resolved.
        return StepResult(
            name=self.name,
            status="changed",
            detail=(
                f"WARNING: TLS cert failed for {cert_host} — using self-signed. "
                "Connection pages will show cert warnings. "
                "Check port 80 is open and domain resolves correctly"
            ),
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
            error = upload_pwa_assets(conn)
        except Exception as exc:
            return StepResult(
                name=self.name,
                status="failed",
                detail=f"Failed to load PWA assets: {exc}",
            )
        if error:
            return StepResult(
                name=self.name,
                status="failed",
                detail=error,
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

        xhttp_url = ""
        if xhttp_enabled and xhttp_path:
            # Use domain if available, otherwise IP
            xhttp_host = domain or self.server_ip
            xhttp_url = (
                f"vless://{reality_uuid}@{xhttp_host}:443"
                f"?encryption=none&security=tls&sni={xhttp_host}&fp={self.fingerprint}"
                f"&type=xhttp&path=%2F{xhttp_path}#VLESS-XHTTP"
            )

        # Generate QR codes as base64 PNG (pure Python, no qrencode binary needed)
        from meridian.urls import generate_qr_base64

        reality_qr_b64 = generate_qr_base64(reality_url)
        wss_qr_b64 = generate_qr_base64(wss_url) if wss_url else ""
        xhttp_qr_b64 = generate_qr_base64(xhttp_url) if xhttp_url else ""

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
        conn.run("mkdir -p /etc/meridian", timeout=15)
        conn.run(f"printf '%s' {q_script} > /etc/meridian/update-stats.py", timeout=15)
        conn.run("chmod 700 /etc/meridian/update-stats.py", timeout=15)

        # Create stats directory
        conn.run(
            "mkdir -p /var/www/private/stats && chown www-data:www-data /var/www/private/stats",
            timeout=15,
        )

        # Run stats update once
        conn.run("python3 /etc/meridian/update-stats.py", timeout=15)

        # Add cron job (idempotent via crontab manipulation), with syslog logging
        cron_job = "*/5 * * * * python3 /etc/meridian/update-stats.py 2>&1 | logger -t meridian-stats"
        q_cron = shlex.quote(cron_job)
        conn.run(
            f"(crontab -l 2>/dev/null | grep -v 'update-stats.py'; echo {q_cron}) | crontab -",
            timeout=15,
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
        conn.run(f"printf '%s' {q_watchdog} > /etc/meridian/health-check.sh", timeout=15)
        conn.run("chmod 700 /etc/meridian/health-check.sh", timeout=15)

        watchdog_cron = "*/5 * * * * /etc/meridian/health-check.sh 2>&1 | logger -t meridian-health"
        q_wc = shlex.quote(watchdog_cron)
        conn.run(
            f"(crontab -l 2>/dev/null | grep -v 'health-check.sh'; echo {q_wc}) | crontab -",
            timeout=15,
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

        host = domain or self.server_ip
        page_url = f"https://{host}/{info_page_path}/{reality_uuid}/"

        client_files = generate_client_files(
            page_urls,
            server_ip=self.server_ip,
            domain=domain,
            client_name=first_client_name,
            server_name=creds.branding.server_name,
            server_icon=creds.branding.icon,
            color=creds.branding.color,
            page_url=page_url,
        )

        upload_error = upload_client_files(conn, reality_uuid, client_files)
        if upload_error:
            return StepResult(
                name=self.name,
                status="failed",
                detail=upload_error,
            )

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
    result = conn.run(f"dig +short {q_domain} @8.8.8.8", timeout=15)
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
