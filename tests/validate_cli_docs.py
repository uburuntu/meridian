"""Validate that all CLI flags are documented in cli-reference.md.

Runs `meridian <command> --help` for every public command and checks that
each flag appears somewhere in the corresponding section of cli-reference.md.

Usage:
    uv run python tests/validate_cli_docs.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CLI_REFERENCE = ROOT / "website" / "src" / "content" / "docs" / "en" / "cli-reference.md"

# Map CLI commands to their doc heading in cli-reference.md.
# Subcommands share a parent section (e.g. "client add" → "### meridian client").
COMMANDS: dict[str, str] = {
    "deploy": "### meridian deploy",
    "plan": "### meridian plan",
    "apply": "### meridian apply",
    "preflight": "### meridian preflight",
    "scan": "### meridian scan",
    "test": "### meridian test",
    "probe": "### meridian probe",
    "doctor": "### meridian doctor",
    "teardown": "### meridian teardown",
    "update": "### meridian update",
    "client add": "### meridian client",
    "client show": "### meridian client",
    "client list": "### meridian client",
    "client remove": "### meridian client",
    "server add": "### meridian server",
    "server list": "### meridian server",
    "server remove": "### meridian server",
    "relay deploy": "### meridian relay",
    "relay list": "### meridian relay",
    "relay remove": "### meridian relay",
    "relay check": "### meridian relay",
}

# Flags that appear on every command — don't require per-command docs.
SKIP_FLAGS = {"--help", "--version", "--install-completion", "--show-completion"}


def get_flags_from_help(command: str) -> set[str]:
    """Run `meridian <command> --help` and extract all --flag names."""
    args = ["uv", "run", "meridian"] + command.split() + ["--help"]
    result = subprocess.run(args, capture_output=True, text=True)
    output = result.stdout + result.stderr
    flags = set(re.findall(r"--[a-z][\w-]*", output))
    return flags - SKIP_FLAGS


def parse_doc_sections(path: Path) -> dict[str, str]:
    """Split cli-reference.md into sections by ### headings.

    Returns {heading: section_text} including a special "## Global flags" key.
    """
    text = path.read_text()
    sections: dict[str, str] = {}
    current_heading = ""
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("### ") or line.startswith("## "):
            if current_heading:
                sections[current_heading] = "\n".join(current_lines)
            current_heading = line.strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_heading:
        sections[current_heading] = "\n".join(current_lines)

    return sections


def get_flags_in_section(section_text: str) -> set[str]:
    """Extract all --flag references from a doc section."""
    return set(re.findall(r"--[a-z][\w-]*", section_text))


def main() -> int:
    if not CLI_REFERENCE.exists():
        print(f"ERROR: {CLI_REFERENCE} not found")
        return 1

    sections = parse_doc_sections(CLI_REFERENCE)
    global_flags = get_flags_in_section(sections.get("## Global flags", ""))

    errors: list[str] = []

    for command, heading in COMMANDS.items():
        cli_flags = get_flags_from_help(command)
        if not cli_flags:
            continue  # Command has no flags (e.g. update)

        section_text = sections.get(heading, "")
        if not section_text:
            errors.append(f"  {heading}: section not found in cli-reference.md")
            continue

        doc_flags = get_flags_in_section(section_text) | global_flags
        missing = cli_flags - doc_flags

        if missing:
            for flag in sorted(missing):
                errors.append(f"  meridian {command}: {flag} not documented in '{heading}'")

    if errors:
        print("ERROR: Undocumented CLI flags found:\n")
        print("\n".join(errors))
        print(f"\nUpdate {CLI_REFERENCE.relative_to(ROOT)} to fix.")
        return 1

    print(f"OK: All CLI flags documented ({len(COMMANDS)} commands checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
