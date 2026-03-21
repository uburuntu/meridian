"""Connection output generation -- VLESS URLs, QR codes, HTML pages.

Builds VLESS connection URLs and generates output files (HTML, text, QR codes)
for proxy clients.

This module is kept as the backwards-compatible public API.
New code should import from the focused sub-modules directly:
  - ``meridian.urls``    — URL building and QR generation
  - ``meridian.render``  — HTML/text file output
  - ``meridian.display`` — terminal output
"""

from __future__ import annotations

import shlex
import subprocess
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from meridian.credentials import ServerCredentials
from meridian.display import print_terminal_output as _display_print  # noqa: F401
from meridian.protocols import get_protocol
from meridian.render import save_connection_html as _render_save_html  # noqa: F401

# Re-export new API so callers can import either from here or the new modules.
from meridian.urls import build_protocol_urls  # noqa: F401


@dataclass(frozen=True)
class ClientURLs:
    """VLESS connection URLs for a client.

    .. deprecated::
        Use ``build_protocol_urls()`` and ``list[ProtocolURL]`` instead.
        This dataclass will be removed in a future major version.
    """

    name: str
    reality: str
    xhttp: str  # empty string if XHTTP is not enabled
    wss: str  # empty string if domain mode is not enabled


def build_vless_urls(
    name: str,
    reality_uuid: str,
    wss_uuid: str,
    creds: ServerCredentials,
    *,
    xhttp_port: int = 0,
) -> ClientURLs:
    """Build VLESS connection URLs for a client.

    Delegates to protocol classes for URL construction.

    Args:
        name: Client display name (used in URL fragment).
        reality_uuid: UUID for Reality and XHTTP connections.
        wss_uuid: UUID for WSS connection (empty if not domain mode).
        creds: Server credentials with protocol configs.
        xhttp_port: XHTTP inbound port (0 = no XHTTP).

    .. deprecated::
        Use ``build_protocol_urls()`` which returns ``list[ProtocolURL]``
        instead. This function will be removed in a future major version.
    """
    ip = creds.server.ip or ""
    sni = creds.server.sni or "www.microsoft.com"
    public_key = creds.reality.public_key or ""
    short_id = creds.reality.short_id or ""
    domain = creds.server.domain or ""
    ws_path = creds.wss.ws_path or ""

    # Shared kwargs for Reality-based protocols
    reality_kwargs = {
        "ip": ip,
        "sni": sni,
        "public_key": public_key,
        "short_id": short_id,
    }

    # Reality (always present)
    reality_proto = get_protocol("reality")
    if reality_proto is None:
        raise ValueError("Reality protocol not registered -- this is a bug")
    reality_url = reality_proto.build_url(reality_uuid, name, **reality_kwargs)

    # XHTTP (optional, shares Reality UUID)
    xhttp_url = ""
    if xhttp_port > 0:
        xhttp_proto = get_protocol("xhttp")
        if xhttp_proto is None:
            raise ValueError("XHTTP protocol not registered -- this is a bug")
        xhttp_url = xhttp_proto.build_url(reality_uuid, name, port=xhttp_port, **reality_kwargs)

    # WSS (optional, requires domain + own UUID)
    wss_url = ""
    if domain and wss_uuid:
        wss_proto = get_protocol("wss")
        if wss_proto is None:
            raise ValueError("WSS protocol not registered -- this is a bug")
        wss_url = wss_proto.build_url(wss_uuid, name, domain=domain, ws_path=ws_path)

    return ClientURLs(name=name, reality=reality_url, xhttp=xhttp_url, wss=wss_url)


def generate_qr_terminal(url: str) -> str:
    """Generate a QR code for terminal display using qrencode."""
    try:
        result = subprocess.run(
            ["qrencode", "-t", "ANSIUTF8", url],
            capture_output=True,
            text=True,
            timeout=5,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


def generate_qr_base64(url: str) -> str:
    """Generate a QR code as base64-encoded PNG for HTML embedding.

    Uses `base64 | tr -d '\\n'` for macOS compatibility (no -w0).
    """
    try:
        result = subprocess.run(
            ["bash", "-c", f"printf '%s' {shlex.quote(url)} | qrencode -t PNG -o - -s 6 | base64 | tr -d '\\n'"],
            capture_output=True,
            text=True,
            timeout=5,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return ""


def save_connection_text(
    urls: ClientURLs,
    dest: Path,
    server_ip: str,
) -> None:
    """Save a plain-text connection summary file."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "=" * 78,
        f"  Connection Info -- {urls.name}",
        f"  Server: {server_ip}",
        f"  Generated: {now}",
        "=" * 78,
        "",
        "--- Primary: VLESS + Reality (port 443) ---",
        urls.reality,
        "",
    ]

    if urls.xhttp:
        lines.extend(
            [
                "--- XHTTP: VLESS + Reality + XHTTP (enhanced stealth) ---",
                urls.xhttp,
                "",
            ]
        )

    if urls.wss:
        lines.extend(
            [
                "--- Fallback: VLESS + WSS + CDN ---",
                urls.wss,
                "",
            ]
        )

    lines.extend(
        [
            "--- Recommended Client Apps ---",
            "iOS:      v2RayTun (App Store) or Hiddify",
            "Android:  v2rayNG (Play Store) or Hiddify",
            "Windows:  v2rayN (github.com/2dust/v2rayN/releases)",
            "macOS:    Hiddify (github.com/hiddify/hiddify-app/releases)",
            "Linux:    Hiddify or Nekoray",
            "",
            "--- Important ---",
            "1. TIME SYNC: Device clock must be accurate within 30 seconds.",
            '   Enable "Set Automatically" in your device\'s date/time settings.',
            "",
            "2. Open this file in a browser or scan the QR code in the HTML version.",
            "",
            "=" * 78,
        ]
    )

    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest.write_text("\n".join(lines))
    dest.chmod(0o600)


def save_connection_html(
    urls: ClientURLs,
    dest: Path,
    server_ip: str,
    domain: str = "",
) -> None:
    """Save a connection info HTML page with QR codes.

    Generates QR codes as base64 PNGs and embeds them inline.
    Uses the same HTML structure as the Jinja2 template but generated in Python.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    reality_qr = generate_qr_base64(urls.reality)
    xhttp_qr = generate_qr_base64(urls.xhttp) if urls.xhttp else ""
    wss_qr = generate_qr_base64(urls.wss) if urls.wss else ""

    # Build the HTML from the Jinja2 template (read from package)
    try:
        from importlib.resources import files

        template_path = files("meridian") / "templates" / "connection-info.html.j2"
        template_text = template_path.read_text(encoding="utf-8")
    except Exception as e:
        warnings.warn(f"Could not load connection-info template: {e}", stacklevel=2)
        # Fallback: generate a minimal HTML page
        template_text = None

    if template_text:
        html = _render_html_template(
            template_text,
            urls,
            server_ip,
            domain,
            now,
            reality_qr,
            xhttp_qr,
            wss_qr,
        )
    else:
        html = _generate_minimal_html(urls, server_ip, domain, now, reality_qr, xhttp_qr, wss_qr)

    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest.write_text(html)
    dest.chmod(0o600)


def _render_html_template(
    template_text: str,
    urls: ClientURLs,
    server_ip: str,
    domain: str,
    now: str,
    reality_qr: str,
    xhttp_qr: str,
    wss_qr: str,
) -> str:
    """Render the connection-info Jinja2 template with Python variables.

    Uses a minimal Jinja2 rendering approach with simple string substitution.
    """
    import types as _types

    try:
        from jinja2 import TemplateError
    except ImportError:
        TemplateError = Exception  # type: ignore[assignment,misc]

    try:
        from jinja2 import BaseLoader, Environment

        env = Environment(loader=BaseLoader(), autoescape=False)

        # Add 'default' filter (matches Jinja2 built-in semantics)
        def default_filter(value: object, default_value: object = "") -> object:
            if value is None or value == "":
                return default_value
            return value

        env.filters["default"] = default_filter
        env.filters["bool"] = lambda v: str(v).lower() in ("true", "1", "yes")

        tmpl = env.from_string(template_text)
        return tmpl.render(
            vless_reality_url=urls.reality,
            vless_xhttp_url=urls.xhttp,
            vless_wss_url=urls.wss,
            server_public_ip=server_ip,
            domain=domain,
            domain_mode=bool(domain),
            xhttp_enabled=bool(urls.xhttp),
            is_server_hosted=False,
            client_name=urls.name,
            # QR code variables (local-save variant) — SimpleNamespace instead of
            # the old type("obj", ...) dynamic class.
            reality_qr_b64_local=_types.SimpleNamespace(stdout=reality_qr),
            xhttp_qr_b64_local=_types.SimpleNamespace(stdout=xhttp_qr),
            wss_qr_b64_local=_types.SimpleNamespace(stdout=wss_qr),
            generated_at={"iso8601": now},
        )
    except (TemplateError, ImportError, FileNotFoundError, OSError) as e:
        warnings.warn(f"HTML template rendering failed, falling back to minimal HTML: {e}", stacklevel=2)
        return _generate_minimal_html(urls, server_ip, domain, now, reality_qr, xhttp_qr, wss_qr)


def _generate_minimal_html(
    urls: ClientURLs,
    server_ip: str,
    domain: str,
    now: str,
    reality_qr: str,
    xhttp_qr: str,
    wss_qr: str,
) -> str:
    """Generate a minimal HTML page when the template is not available."""
    cards = [_html_card("Primary (Reality)", urls.reality, reality_qr)]
    if urls.xhttp:
        cards.append(_html_card("XHTTP (Stealth)", urls.xhttp, xhttp_qr))
    if urls.wss:
        cards.append(_html_card("CDN Backup (WSS)", urls.wss, wss_qr))

    ping_url = f"https://meridian.msu.rocks/ping?ip={server_ip}"
    if domain:
        ping_url += f"&domain={domain}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Connection Setup - {urls.name}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
background:#0c0e14;color:#e8eaf0;margin:0;padding:24px 16px}}
.wrap{{max-width:460px;margin:0 auto}}
h1{{font-size:1.3rem;text-align:center;margin-bottom:4px}}
.sub{{text-align:center;color:#8b90a8;font-size:.82rem;margin-bottom:24px}}
.card{{background:#181c28;border:1px solid #282d3e;border-radius:14px;padding:20px;margin-bottom:14px}}
.card h2{{font-size:.9rem;color:#5b9cf5;margin-bottom:12px}}
.qr{{text-align:center;margin:12px 0}}
.qr img{{width:200px;height:200px;border-radius:8px;background:#fff;padding:6px}}
.url{{background:#12151e;border:1px solid #282d3e;border-radius:8px;padding:10px;
font-family:monospace;font-size:.65rem;word-break:break-all;color:#555a72;cursor:pointer}}
a.btn{{display:block;background:#5b9cf5;color:#fff;text-align:center;padding:13px;
border-radius:10px;text-decoration:none;font-weight:600;margin-bottom:12px}}
.foot{{text-align:center;color:#555a72;font-size:.7rem;margin-top:24px}}
.foot a{{color:#8b90a8;text-decoration:none}}
</style>
</head>
<body>
<div class="wrap">
<h1>Connection Setup</h1>
<p class="sub">{urls.name} &middot; {server_ip}</p>
{"".join(cards)}
<div class="card">
<h2>Not connecting?</h2>
<p style="font-size:.82rem;color:#8b90a8">
Test server reachability: <a href="{ping_url}" target="_blank" style="color:#e5a44e">Run ping test</a>
</p>
</div>
<div class="foot">
<a href="https://meridian.msu.rocks">Powered by Meridian</a> &middot; {now}
</div>
</div>
<script>
document.querySelectorAll('.url').forEach(function(el){{
el.onclick=function(){{navigator.clipboard&&navigator.clipboard.writeText(el.textContent)}}}})
</script>
</body>
</html>"""


def _html_card(title: str, url: str, qr_b64: str) -> str:
    """Generate a single protocol card for the minimal HTML page."""
    qr_html = f'<div class="qr"><img src="data:image/png;base64,{qr_b64}" alt="QR"></div>' if qr_b64 else ""
    return f"""<div class="card">
<h2>{title}</h2>
<a class="btn" href="{url}">Open in App</a>
{qr_html}
<div class="url">{url}</div>
</div>
"""


def print_terminal_output(
    urls: ClientURLs,
    creds_dir: Path,
    server_ip: str,
) -> None:
    """Print connection info with QR codes to the terminal."""
    from meridian.console import err_console

    # Generate QR codes
    reality_qr = generate_qr_terminal(urls.reality)
    if reality_qr:
        err_console.print()
        # Print raw QR code (ANSI) without Rich markup processing
        print(reality_qr, end="")

    if urls.xhttp:
        xhttp_qr = generate_qr_terminal(urls.xhttp)
        if xhttp_qr:
            err_console.print()
            print(xhttp_qr, end="")

    if urls.wss:
        wss_qr = generate_qr_terminal(urls.wss)
        if wss_qr:
            err_console.print()
            print(wss_qr, end="")

    # Print summary
    err_console.print()
    err_console.print(f'  [bold green]\u2713[/bold green] [bold]Client "{urls.name}" added[/bold]')
    err_console.print()
    err_console.print("  [bold]Connection URLs:[/bold]")
    err_console.print("  [info]Primary (Reality):[/info]")
    err_console.print(f"  {urls.reality}")

    if urls.xhttp:
        err_console.print("\n  [info]XHTTP (enhanced stealth):[/info]")
        err_console.print(f"  {urls.xhttp}")

    if urls.wss:
        err_console.print("\n  [info]CDN fallback (WSS):[/info]")
        err_console.print(f"  {urls.wss}")

    # Find saved files
    html_files = list(creds_dir.glob(f"*-{urls.name}-connection-info.html"))
    txt_files = list(creds_dir.glob(f"*-{urls.name}-connection-info.txt"))

    if html_files or txt_files:
        err_console.print("\n  [bold]Files Saved:[/bold]")
        if html_files:
            err_console.print(f"  HTML page: [bold]{html_files[0]}[/bold]")
        if txt_files:
            err_console.print(f"  Text file: {txt_files[0]}")

    err_console.print()
    err_console.print(f"  Send the HTML file to {urls.name} --")
    err_console.print("  they open it, scan the QR code, and connect.")
    err_console.print()
