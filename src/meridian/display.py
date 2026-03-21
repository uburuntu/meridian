"""Terminal output for connection info."""

from __future__ import annotations

from pathlib import Path

from meridian.models import ProtocolURL, derive_client_name
from meridian.urls import generate_qr_terminal


def print_terminal_output(
    protocol_urls: list[ProtocolURL],
    creds_dir: Path,
    server_ip: str,
    *,
    client_name: str = "",
    hosted_page_url: str = "",
) -> None:
    """Print connection info with QR codes to the terminal.

    Args:
        protocol_urls: Ordered list of active protocol URLs.
        creds_dir: Credentials directory (used to locate saved output files).
        server_ip: Server IP address for display.
        client_name: Client name for the summary header (derived from the
            first URL fragment when omitted).
        hosted_page_url: If set, show this URL as the shareable link.
    """
    from meridian.console import err_console

    # Derive client name.
    name = client_name or derive_client_name(protocol_urls)

    # Print QR codes for each active protocol.
    for purl in protocol_urls:
        if not purl.url:
            continue
        qr = generate_qr_terminal(purl.url)
        if qr:
            err_console.print()
            print(qr, end="")

    # Print summary.
    err_console.print()
    err_console.print(f'  [bold green]\u2713[/bold green] [bold]Client "{name}" added[/bold]')
    err_console.print()
    err_console.print("  [bold]Connection URLs:[/bold]")

    first = True
    for purl in protocol_urls:
        if not purl.url:
            continue
        if first:
            err_console.print(f"  [info]{purl.label} (Reality):[/info]")
            err_console.print(f"  {purl.url}")
            first = False
        elif purl.key == "xhttp":
            err_console.print("\n  [info]XHTTP (enhanced stealth):[/info]")
            err_console.print(f"  {purl.url}")
        elif purl.key == "wss":
            err_console.print("\n  [info]CDN fallback (WSS):[/info]")
            err_console.print(f"  {purl.url}")
        else:
            err_console.print(f"\n  [info]{purl.label}:[/info]")
            err_console.print(f"  {purl.url}")

    # Find saved files.
    html_files = list(creds_dir.glob(f"*-{name}-connection-info.html"))
    txt_files = list(creds_dir.glob(f"*-{name}-connection-info.txt"))

    if html_files or txt_files:
        err_console.print("\n  [bold]Files Saved:[/bold]")
        if html_files:
            err_console.print(f"  HTML page: [bold]{html_files[0]}[/bold]")
        if txt_files:
            err_console.print(f"  Text file: {txt_files[0]}")

    if hosted_page_url:
        err_console.print()
        err_console.print(f"  [bold]Shareable link:[/bold] [ok]{hosted_page_url}[/ok]")
        err_console.print()
        err_console.print(f"  Send this URL to {name} --")
        err_console.print("  they open it, scan the QR code, and connect.")
    else:
        err_console.print()
        err_console.print(f"  Send the HTML file to {name} --")
        err_console.print("  they open it, scan the QR code, and connect.")
    err_console.print()
