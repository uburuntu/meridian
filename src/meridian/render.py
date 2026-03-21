"""File output rendering — HTML and text connection summaries."""

from __future__ import annotations

import types
from datetime import datetime, timezone
from pathlib import Path

from meridian.models import ProtocolURL
from meridian.urls import generate_qr_base64


def save_connection_text(
    protocol_urls: list[ProtocolURL],
    dest: Path,
    server_ip: str,
    *,
    client_name: str = "",
) -> None:
    """Save a plain-text connection summary file.

    Args:
        protocol_urls: Ordered list of active protocol URLs.
        dest: Destination file path.
        server_ip: Server IP address for display.
        client_name: Client name for the header (derived from URL fragments
            if omitted).
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Derive client name from first URL if not explicitly provided.
    name = client_name
    if not name and protocol_urls:
        # Best-effort: strip the URL fragment.
        frag = protocol_urls[0].url.rsplit("#", 1)
        name = frag[-1] if len(frag) > 1 else "client"

    lines = [
        "=" * 78,
        f"  Connection Info -- {name}",
        f"  Server: {server_ip}",
        f"  Generated: {now}",
        "=" * 78,
        "",
    ]

    for purl in protocol_urls:
        if not purl.url:
            continue
        if purl.key == "reality":
            lines.extend(
                [
                    "--- Primary: VLESS + Reality (port 443) ---",
                    purl.url,
                    "",
                ]
            )
        elif purl.key == "xhttp":
            lines.extend(
                [
                    "--- XHTTP: VLESS + Reality + XHTTP (enhanced stealth) ---",
                    purl.url,
                    "",
                ]
            )
        elif purl.key == "wss":
            lines.extend(
                [
                    "--- Fallback: VLESS + WSS + CDN ---",
                    purl.url,
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    f"--- {purl.label} ---",
                    purl.url,
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
    protocol_urls: list[ProtocolURL],
    dest: Path,
    server_ip: str,
    domain: str = "",
    *,
    client_name: str = "",
) -> None:
    """Save a connection info HTML page with QR codes.

    Generates QR codes as base64 PNGs and embeds them inline.
    Uses the same HTML structure as the Ansible template when available,
    falling back to a minimal self-contained HTML page.

    Args:
        protocol_urls: Ordered list of active protocol URLs.
        dest: Destination file path.
        server_ip: Server IP address for display.
        domain: Optional domain name (enables WSS card in template).
        client_name: Client name for the page title (derived from URLs if
            omitted).
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Derive client name.
    name = client_name
    if not name and protocol_urls:
        frag = protocol_urls[0].url.rsplit("#", 1)
        name = frag[-1] if len(frag) > 1 else "client"

    # Build per-protocol QR data.
    qr_map: dict[str, str] = {}
    for purl in protocol_urls:
        if purl.url:
            qr_map[purl.key] = generate_qr_base64(purl.url)

    reality_url = next((p.url for p in protocol_urls if p.key == "reality"), "")
    xhttp_url = next((p.url for p in protocol_urls if p.key == "xhttp"), "")
    wss_url = next((p.url for p in protocol_urls if p.key == "wss"), "")

    reality_qr = qr_map.get("reality", "")
    xhttp_qr = qr_map.get("xhttp", "")
    wss_qr = qr_map.get("wss", "")

    # Try rendering the bundled Jinja2 template.
    try:
        from importlib.resources import files

        template_path = files("meridian") / "playbooks" / "roles" / "shared" / "templates" / "connection-info.html.j2"
        template_text: str | None = template_path.read_text(encoding="utf-8")
    except Exception:
        template_text = None

    if template_text:
        html = _render_html_template(
            template_text,
            name,
            reality_url,
            xhttp_url,
            wss_url,
            server_ip,
            domain,
            now,
            reality_qr,
            xhttp_qr,
            wss_qr,
        )
    else:
        html = _generate_minimal_html(
            name,
            protocol_urls,
            qr_map,
            server_ip,
            domain,
            now,
        )

    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest.write_text(html)
    dest.chmod(0o600)


def _render_html_template(
    template_text: str,
    client_name: str,
    reality_url: str,
    xhttp_url: str,
    wss_url: str,
    server_ip: str,
    domain: str,
    now: str,
    reality_qr: str,
    xhttp_qr: str,
    wss_qr: str,
) -> str:
    """Render the connection-info Jinja2 template with Python variables."""
    try:
        from jinja2 import BaseLoader, Environment

        env = Environment(loader=BaseLoader(), autoescape=False)

        def default_filter(value: object, default_value: object = "") -> object:
            if value is None or value == "":
                return default_value
            return value

        env.filters["default"] = default_filter
        env.filters["bool"] = lambda v: str(v).lower() in ("true", "1", "yes")

        tmpl = env.from_string(template_text)
        return tmpl.render(
            vless_reality_url=reality_url,
            vless_xhttp_url=xhttp_url,
            vless_wss_url=wss_url,
            server_public_ip=server_ip,
            domain=domain,
            domain_mode=bool(domain),
            xhttp_enabled=bool(xhttp_url),
            is_server_hosted=False,
            client_name=client_name,
            # QR code variables (local-save variant) — use SimpleNamespace
            # instead of the old type("obj", ...) dynamic class hack.
            reality_qr_b64_local=types.SimpleNamespace(stdout=reality_qr),
            xhttp_qr_b64_local=types.SimpleNamespace(stdout=xhttp_qr),
            wss_qr_b64_local=types.SimpleNamespace(stdout=wss_qr),
            ansible_date_time={"iso8601": now},
        )
    except Exception:
        from meridian.models import ProtocolURL as _PU

        purls = []
        if reality_url:
            purls.append(_PU(key="reality", label="Primary", url=reality_url))
        if xhttp_url:
            purls.append(_PU(key="xhttp", label="XHTTP", url=xhttp_url))
        if wss_url:
            purls.append(_PU(key="wss", label="CDN Backup", url=wss_url))

        qr_map: dict[str, str] = {
            "reality": reality_qr,
            "xhttp": xhttp_qr,
            "wss": wss_qr,
        }
        return _generate_minimal_html(client_name, purls, qr_map, server_ip, domain, now)


def _generate_minimal_html(
    client_name: str,
    protocol_urls: list[ProtocolURL],
    qr_map: dict[str, str],
    server_ip: str,
    domain: str,
    now: str,
) -> str:
    """Generate a minimal HTML page when the Jinja2 template is not available."""
    cards = "".join(_html_card(purl.label, purl.url, qr_map.get(purl.key, "")) for purl in protocol_urls if purl.url)

    ping_url = f"https://meridian.msu.rocks/ping?ip={server_ip}"
    if domain:
        ping_url += f"&domain={domain}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Connection Setup - {client_name}</title>
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
<p class="sub">{client_name} &middot; {server_ip}</p>
{cards}
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
