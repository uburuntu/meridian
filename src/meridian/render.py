"""File output rendering — HTML and text connection summaries."""

from __future__ import annotations

import html as html_mod
import types
from datetime import datetime, timezone
from pathlib import Path

from meridian.models import ProtocolURL, derive_client_name
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
    name = client_name or derive_client_name(protocol_urls)

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
    Uses the same HTML structure as the Jinja2 template when available,
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
    name = client_name or derive_client_name(protocol_urls)

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

    # Build template variables — local-save uses *_local QR variable names.
    variables = _build_template_variables(
        client_name=name,
        reality_url=reality_url,
        xhttp_url=xhttp_url,
        wss_url=wss_url,
        server_ip=server_ip,
        domain=domain,
        now=now,
        is_server_hosted=False,
        reality_qr_b64=reality_qr,
        xhttp_qr_b64=xhttp_qr,
        wss_qr_b64=wss_qr,
    )

    result_html = _render_template(
        template_text=_load_template_text(),
        variables=variables,
        client_name=name,
        reality_url=reality_url,
        xhttp_url=xhttp_url,
        wss_url=wss_url,
        reality_qr=reality_qr,
        xhttp_qr=xhttp_qr,
        wss_qr=wss_qr,
        server_ip=server_ip,
        domain=domain,
        now=now,
    )

    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest.write_text(result_html)
    dest.chmod(0o600)


def render_hosted_html(
    reality_url: str,
    server_ip: str,
    domain: str = "",
    *,
    xhttp_url: str = "",
    wss_url: str = "",
    client_name: str = "",
    reality_qr_b64: str = "",
    xhttp_qr_b64: str = "",
    wss_qr_b64: str = "",
) -> str:
    """Render connection info HTML for server hosting (is_server_hosted=True).

    Returns the rendered HTML string. Used by the provisioner's
    DeployConnectionPage step and by ``client add`` for server-hosted pages.

    Args:
        reality_url: VLESS Reality connection URL.
        server_ip: Server IP address.
        domain: Optional domain (enables WSS card).
        xhttp_url: Optional XHTTP connection URL.
        wss_url: Optional WSS connection URL.
        client_name: Client name for page title.
        reality_qr_b64: Base64-encoded QR PNG for Reality URL.
        xhttp_qr_b64: Base64-encoded QR PNG for XHTTP URL.
        wss_qr_b64: Base64-encoded QR PNG for WSS URL.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build template variables — server-hosted uses non-_local QR variable names.
    variables = _build_template_variables(
        client_name=client_name,
        reality_url=reality_url,
        xhttp_url=xhttp_url,
        wss_url=wss_url,
        server_ip=server_ip,
        domain=domain,
        now=now,
        is_server_hosted=True,
        reality_qr_b64=reality_qr_b64,
        xhttp_qr_b64=xhttp_qr_b64,
        wss_qr_b64=wss_qr_b64,
    )

    return _render_template(
        template_text=_load_template_text(),
        variables=variables,
        client_name=client_name,
        reality_url=reality_url,
        xhttp_url=xhttp_url,
        wss_url=wss_url,
        reality_qr=reality_qr_b64,
        xhttp_qr=xhttp_qr_b64,
        wss_qr=wss_qr_b64,
        server_ip=server_ip,
        domain=domain,
        now=now,
    )


# ---------------------------------------------------------------------------
# Shared internal helpers
# ---------------------------------------------------------------------------


def _load_template_text() -> str | None:
    """Load the bundled Jinja2 connection-info template.

    Returns the template text or None if not available.
    """
    try:
        from importlib.resources import files

        template_path = files("meridian") / "templates" / "connection-info.html.j2"
        return template_path.read_text(encoding="utf-8")
    except Exception:
        return None


def _build_template_variables(
    *,
    client_name: str,
    reality_url: str,
    xhttp_url: str,
    wss_url: str,
    server_ip: str,
    domain: str,
    now: str,
    is_server_hosted: bool,
    reality_qr_b64: str,
    xhttp_qr_b64: str,
    wss_qr_b64: str,
) -> dict[str, object]:
    """Build the Jinja2 template variable dict.

    Server-hosted pages use ``reality_qr_b64`` etc., while local-save pages
    use ``reality_qr_b64_local`` etc.  Both variants wrap the base64 string
    in a SimpleNamespace with a ``.stdout`` attribute (matching the template's
    ``{{ var.stdout }}`` access pattern).
    """
    variables: dict[str, object] = {
        "vless_reality_url": reality_url,
        "vless_xhttp_url": xhttp_url,
        "vless_wss_url": wss_url,
        "server_public_ip": server_ip,
        "domain": domain,
        "domain_mode": bool(domain),
        "xhttp_enabled": bool(xhttp_url),
        "is_server_hosted": is_server_hosted,
        "client_name": client_name,
        "generated_at": {"iso8601": now},
    }

    if is_server_hosted:
        variables["reality_qr_b64"] = types.SimpleNamespace(stdout=reality_qr_b64)
        variables["xhttp_qr_b64"] = types.SimpleNamespace(stdout=xhttp_qr_b64)
        variables["wss_qr_b64"] = types.SimpleNamespace(stdout=wss_qr_b64)
    else:
        variables["reality_qr_b64_local"] = types.SimpleNamespace(stdout=reality_qr_b64)
        variables["xhttp_qr_b64_local"] = types.SimpleNamespace(stdout=xhttp_qr_b64)
        variables["wss_qr_b64_local"] = types.SimpleNamespace(stdout=wss_qr_b64)

    return variables


def _render_template(
    template_text: str | None,
    variables: dict[str, object],
    *,
    client_name: str,
    reality_url: str,
    xhttp_url: str,
    wss_url: str,
    reality_qr: str,
    xhttp_qr: str,
    wss_qr: str,
    server_ip: str,
    domain: str,
    now: str,
) -> str:
    """Render the Jinja2 template with variables, falling back to minimal HTML.

    Args:
        template_text: The Jinja2 template source, or None if unavailable.
        variables: Template variable dict (from ``_build_template_variables``).
        client_name: Client name (for fallback).
        reality_url: Reality URL (for fallback).
        xhttp_url: XHTTP URL (for fallback).
        wss_url: WSS URL (for fallback).
        reality_qr: Base64 QR for Reality (for fallback).
        xhttp_qr: Base64 QR for XHTTP (for fallback).
        wss_qr: Base64 QR for WSS (for fallback).
        server_ip: Server IP (for fallback).
        domain: Domain (for fallback).
        now: ISO 8601 timestamp (for fallback).
    """
    if template_text:
        try:
            from jinja2 import TemplateError
        except ImportError:
            TemplateError = Exception  # type: ignore[assignment,misc]

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
            return tmpl.render(**variables)
        except (TemplateError, ImportError, FileNotFoundError, OSError):
            pass

    # Fallback: minimal HTML
    purls = []
    if reality_url:
        purls.append(ProtocolURL(key="reality", label="Primary", url=reality_url))
    if xhttp_url:
        purls.append(ProtocolURL(key="xhttp", label="XHTTP", url=xhttp_url))
    if wss_url:
        purls.append(ProtocolURL(key="wss", label="CDN Backup", url=wss_url))

    qr_map = {"reality": reality_qr, "xhttp": xhttp_qr, "wss": wss_qr}
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
    safe_name = html_mod.escape(client_name)
    safe_ip = html_mod.escape(server_ip)
    safe_domain = html_mod.escape(domain)
    safe_now = html_mod.escape(now)

    cards = "".join(_html_card(purl.label, purl.url, qr_map.get(purl.key, "")) for purl in protocol_urls if purl.url)

    ping_url = f"https://getmeridian.org/ping?ip={html_mod.escape(server_ip)}"
    if domain:
        ping_url += f"&domain={safe_domain}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Connection Setup - {safe_name}</title>
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
<p class="sub">{safe_name} &middot; {safe_ip}</p>
{cards}
<div class="card">
<h2>Not connecting?</h2>
<p style="font-size:.82rem;color:#8b90a8">
Test server reachability: <a href="{ping_url}" target="_blank" style="color:#e5a44e">Run ping test</a>
</p>
</div>
<div class="foot">
<a href="https://getmeridian.org">Powered by Meridian</a> &middot; {safe_now}
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
    safe_title = html_mod.escape(title)
    safe_url = html_mod.escape(url)
    safe_qr = html_mod.escape(qr_b64)
    qr_html = f'<div class="qr"><img src="data:image/png;base64,{safe_qr}" alt="QR"></div>' if qr_b64 else ""
    return f"""<div class="card">
<h2>{safe_title}</h2>
<a class="btn" href="{safe_url}">Open in App</a>
{qr_html}
<div class="url">{safe_url}</div>
</div>
"""
