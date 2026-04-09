"""Terminal output for connection info."""

from __future__ import annotations

from pathlib import Path

from meridian.models import ProtocolURL, RelayURLSet, derive_client_name
from meridian.urls import generate_qr_terminal


def print_terminal_output(
    protocol_urls: list[ProtocolURL],
    creds_dir: Path,
    server_ip: str,
    *,
    client_name: str = "",
    hosted_page_url: str = "",
    relay_entries: list[RelayURLSet] | None = None,
    header_verb: str = "added",
) -> None:
    """Print connection info with QR codes to the terminal.

    Args:
        protocol_urls: Ordered list of active protocol URLs.
        creds_dir: Credentials directory (used to locate saved output files).
        server_ip: Server IP address for display.
        client_name: Client name for the summary header (derived from the
            first URL fragment when omitted).
        hosted_page_url: If set, show this URL as the shareable link.
        relay_entries: Optional relay URL sets. When present, relay URLs are
            shown first as "Recommended", direct URLs as "Backup".
        header_verb: Action word for the header (e.g., "added", "connection info").
    """
    from meridian.console import err_console

    # Derive client name.
    name = client_name or derive_client_name(protocol_urls)

    # Print summary header.
    err_console.print()
    err_console.print(f'  [bold green]\u2713[/bold green] [bold]Client "{name}" -- {header_verb}[/bold]')
    err_console.print()

    # Shareable link first (most important for "share with family" use case).
    if hosted_page_url:
        err_console.print("  [bold]Share this link:[/bold]")
        err_console.print(f"  [ok]{hosted_page_url}[/ok]")
        err_console.print()
        err_console.print(f"  Send this URL to {name} --")
        err_console.print("  they open it, scan the QR code, and connect.")
        err_console.print()
        err_console.print("  " + "\u2500" * 50)

    # Relay URLs first (if any)
    if relay_entries:
        for relay_set in relay_entries:
            relay_label = relay_set.relay_name or relay_set.relay_ip
            err_console.print()
            err_console.print(f"  [bold green]* Recommended (via relay {relay_label}):[/bold green]")
            for purl in relay_set.urls:
                if not purl.url:
                    continue
                qr = generate_qr_terminal(purl.url)
                if qr:
                    err_console.print()
                    print(qr, end="")
                err_console.print(f"  {purl.url}")

        err_console.print()
        err_console.print("  " + "\u2500" * 50)
        err_console.print()
        err_console.print("  [bold dim]Backup (direct):[/bold dim]")
    else:
        # QR code for the primary (first) protocol.
        for purl in protocol_urls:
            if not purl.url:
                continue
            qr = generate_qr_terminal(purl.url)
            if qr:
                err_console.print()
                print(qr, end="")
            break  # only the primary protocol QR

    # Find saved files.
    html_files = list(creds_dir.glob(f"*-{name}-connection-info.html"))

    if html_files:
        err_console.print()
        err_console.print("  [bold]Saved files:[/bold]")
        err_console.print(f"  HTML page: [bold]{html_files[0]}[/bold]")

    # Connection URLs (raw VLESS URLs for power users).
    err_console.print()
    err_console.print("  [bold]Connection URLs:[/bold]")

    first = True
    for purl in protocol_urls:
        if not purl.url:
            continue
        if first:
            err_console.print(f"  [info]{purl.label}:[/info]")
            err_console.print(f"  {purl.url}")
            first = False
        else:
            err_console.print(f"\n  [info]{purl.label}:[/info]")
            err_console.print(f"  {purl.url}")

    if not hosted_page_url:
        err_console.print()
        if html_files:
            err_console.print(f"  Send the HTML file to {name} --")
        else:
            err_console.print(f"  Share a connection URL with {name} --")
        err_console.print("  they open it, scan the QR code, and connect.")
    err_console.print()
