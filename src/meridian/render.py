"""File output rendering — HTML and text connection summaries."""

from __future__ import annotations

import html as html_mod
import types
from datetime import datetime, timezone
from pathlib import Path

from meridian.models import ProtocolURL, RelayURLSet, derive_client_name
from meridian.urls import generate_qr_base64


def save_connection_text(
    protocol_urls: list[ProtocolURL],
    dest: Path,
    server_ip: str,
    *,
    client_name: str = "",
    relay_entries: list[RelayURLSet] | None = None,
) -> None:
    """Save a plain-text connection summary file.

    Args:
        protocol_urls: Ordered list of active protocol URLs.
        dest: Destination file path.
        server_ip: Server IP address for display.
        client_name: Client name for the header (derived from URL fragments
            if omitted).
        relay_entries: Optional list of relay URL sets. When present, relay
            URLs are shown first as "Recommended", direct URLs as "Backup".
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

    # Relay URLs first (if any)
    if relay_entries:
        for relay_set in relay_entries:
            relay_label = relay_set.relay_name or relay_set.relay_ip
            lines.append(f"--- * Recommended: via relay ({relay_label}) ---")
            for purl in relay_set.urls:
                if purl.url:
                    lines.extend([purl.url, ""])
        lines.append("--- Backup: direct connection ---")
        lines.append("")

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
    relay_entries: list[RelayURLSet] | None = None,
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
        relay_entries: Optional relay URL sets for relay-aware rendering.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Derive client name.
    name = client_name or derive_client_name(protocol_urls)

    # Attach QR codes to protocol URLs (ProtocolURL is frozen, so use replace).
    from dataclasses import replace

    urls_with_qr = [
        replace(p, qr_b64=generate_qr_base64(p.url)) if p.url and not p.qr_b64 else p for p in protocol_urls
    ]

    # Build template variables — local-save uses *_local QR variable names.
    variables = _build_template_variables(
        protocol_urls=urls_with_qr,
        server_ip=server_ip,
        domain=domain,
        now=now,
        is_server_hosted=False,
        client_name=name,
        relay_entries=relay_entries,
    )

    result_html = _render_template(
        template_text=_load_template_text(),
        variables=variables,
        protocol_urls=urls_with_qr,
        server_ip=server_ip,
        domain=domain,
        client_name=name,
        now=now,
    )

    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest.write_text(result_html)
    dest.chmod(0o600)


def render_hosted_html(
    protocol_urls: list[ProtocolURL],
    server_ip: str,
    domain: str = "",
    *,
    client_name: str = "",
    relay_entries: list[RelayURLSet] | None = None,
) -> str:
    """Render connection info HTML for server hosting (is_server_hosted=True).

    Returns the rendered HTML string. Used by the provisioner's
    DeployConnectionPage step and by ``client add`` for server-hosted pages.

    Each ``ProtocolURL`` should have its ``qr_b64`` field populated
    before calling this function.

    Args:
        protocol_urls: Ordered list of active protocol URLs with QR data.
        server_ip: Server IP address.
        domain: Optional domain (enables WSS card).
        client_name: Client name for page title.
        relay_entries: Optional relay URL sets for relay-aware rendering.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    variables = _build_template_variables(
        protocol_urls=protocol_urls,
        server_ip=server_ip,
        domain=domain,
        now=now,
        is_server_hosted=True,
        client_name=client_name,
        relay_entries=relay_entries,
    )

    return _render_template(
        template_text=_load_template_text(),
        variables=variables,
        protocol_urls=protocol_urls,
        server_ip=server_ip,
        domain=domain,
        client_name=client_name,
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


def _url_by_key(protocol_urls: list[ProtocolURL], key: str) -> str:
    """Get URL string for a protocol key, or empty string."""
    return next((p.url for p in protocol_urls if p.key == key), "")


def _qr_by_key(protocol_urls: list[ProtocolURL], key: str) -> str:
    """Get QR base64 for a protocol key, or empty string."""
    return next((p.qr_b64 for p in protocol_urls if p.key == key), "")


def _build_template_variables(
    *,
    protocol_urls: list[ProtocolURL],
    server_ip: str,
    domain: str,
    now: str,
    is_server_hosted: bool,
    client_name: str = "",
    relay_entries: list[RelayURLSet] | None = None,
) -> dict[str, object]:
    """Build the Jinja2 template variable dict.

    Server-hosted pages use ``reality_qr_b64`` etc., while local-save pages
    use ``reality_qr_b64_local`` etc.  Both variants wrap the base64 string
    in a SimpleNamespace with a ``.stdout`` attribute (matching the template's
    ``{{ var.stdout }}`` access pattern).
    """
    reality_url = _url_by_key(protocol_urls, "reality")
    xhttp_url = _url_by_key(protocol_urls, "xhttp")
    wss_url = _url_by_key(protocol_urls, "wss")
    reality_qr = _qr_by_key(protocol_urls, "reality")
    xhttp_qr = _qr_by_key(protocol_urls, "xhttp")
    wss_qr = _qr_by_key(protocol_urls, "wss")

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
        variables["reality_qr_b64"] = types.SimpleNamespace(stdout=reality_qr)
        variables["xhttp_qr_b64"] = types.SimpleNamespace(stdout=xhttp_qr)
        variables["wss_qr_b64"] = types.SimpleNamespace(stdout=wss_qr)
    else:
        variables["reality_qr_b64_local"] = types.SimpleNamespace(stdout=reality_qr)
        variables["xhttp_qr_b64_local"] = types.SimpleNamespace(stdout=xhttp_qr)
        variables["wss_qr_b64_local"] = types.SimpleNamespace(stdout=wss_qr)

    # Relay entries (if any)
    if relay_entries:
        relay_data = []
        for relay_set in relay_entries:
            relay_urls_data = []
            for purl in relay_set.urls:
                if purl.url:
                    qr = purl.qr_b64 or generate_qr_base64(purl.url)
                    relay_urls_data.append(
                        {
                            "key": purl.key,
                            "label": purl.label,
                            "url": purl.url,
                            "qr_b64": qr,
                        }
                    )
            if not relay_urls_data:
                continue  # skip relay entries with no valid URLs
            relay_data.append(
                {
                    "ip": relay_set.relay_ip,
                    "name": relay_set.relay_name,
                    "urls": relay_urls_data,
                    # Keep first URL for backwards compat with template
                    "url": relay_urls_data[0]["url"] if relay_urls_data else "",
                    "qr_b64": relay_urls_data[0]["qr_b64"] if relay_urls_data else "",
                }
            )
        variables["relays"] = relay_data
        variables["has_relays"] = True
    else:
        variables["relays"] = []
        variables["has_relays"] = False

    return variables


def _render_template(
    template_text: str | None,
    variables: dict[str, object],
    *,
    protocol_urls: list[ProtocolURL],
    server_ip: str,
    domain: str,
    client_name: str,
    now: str,
) -> str:
    """Render the Jinja2 template with variables, falling back to minimal HTML.

    Args:
        template_text: The Jinja2 template source, or None if unavailable.
        variables: Template variable dict (from ``_build_template_variables``).
        protocol_urls: Protocol URLs with QR data (for fallback rendering).
        server_ip: Server IP (for fallback).
        domain: Domain (for fallback).
        client_name: Client name (for fallback).
        now: ISO 8601 timestamp (for fallback).
    """
    if template_text:
        try:
            from jinja2 import TemplateError
        except ImportError:
            TemplateError = Exception  # type: ignore[assignment,misc]

        try:
            from jinja2 import BaseLoader, Environment

            env = Environment(loader=BaseLoader(), autoescape=True)

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

    # Fallback: minimal HTML — use protocol_urls directly
    qr_map = {p.key: p.qr_b64 for p in protocol_urls if p.qr_b64}

    # Extract relay entries from variables for fallback rendering
    relay_data_raw = variables.get("relays")
    fallback_relays: list[RelayURLSet] | None = None
    if relay_data_raw and isinstance(relay_data_raw, list):
        fallback_relays = []
        for rd in relay_data_raw:
            if isinstance(rd, dict) and rd.get("url"):
                fallback_relays.append(
                    RelayURLSet(
                        relay_ip=rd["ip"],
                        relay_name=rd.get("name", ""),
                        urls=[ProtocolURL(key="reality", label="Primary (via relay)", url=rd["url"])],
                    )
                )
    return _generate_minimal_html(
        client_name, protocol_urls, qr_map, server_ip, domain, now, relay_entries=fallback_relays
    )


def _generate_minimal_html(
    client_name: str,
    protocol_urls: list[ProtocolURL],
    qr_map: dict[str, str],
    server_ip: str,
    domain: str,
    now: str,
    relay_entries: list[RelayURLSet] | None = None,
) -> str:
    """Generate a minimal HTML page when the Jinja2 template is not available."""
    safe_name = html_mod.escape(client_name)
    safe_ip = html_mod.escape(server_ip)
    safe_domain = html_mod.escape(domain)
    safe_now = html_mod.escape(now)

    cards = ""

    # Relay cards (if any)
    if relay_entries:
        for relay_set in relay_entries:
            relay_label = relay_set.relay_name or relay_set.relay_ip
            for purl in relay_set.urls:
                if purl.url:
                    relay_qr = generate_qr_base64(purl.url)
                    cards += _html_card(f"* Recommended: via {html_mod.escape(relay_label)}", purl.url, relay_qr)
        cards += '<div class="card"><h2 style="color:#e5a44e">Backup (direct)</h2></div>'

    cards += "".join(_html_card(purl.label, purl.url, qr_map.get(purl.key, "")) for purl in protocol_urls if purl.url)

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
