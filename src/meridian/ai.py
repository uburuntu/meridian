"""AI prompt building, clipboard support, and AI docs fetching."""

from __future__ import annotations

import platform
import shutil
import subprocess
import urllib.request

from meridian.config import AI_DOCS_URL, CACHE_DIR
from meridian.console import info, ok, warn


def fetch_ai_docs(version: str) -> str:
    """Fetch AI reference docs, using cache when available."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / "ai-reference.md"
    version_file = CACHE_DIR / "ai-reference.version"

    # Check cache validity
    if cache_file.exists() and version_file.exists():
        cached_version = version_file.read_text().strip()
        if cached_version == version:
            return cache_file.read_text()

    # Fetch fresh
    try:
        req = urllib.request.Request(AI_DOCS_URL)
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode()
        cache_file.write_text(content)
        version_file.write_text(version)
        return content
    except Exception:
        # Fall back to cache even if version doesn't match
        if cache_file.exists():
            warn("Could not fetch latest AI docs, using cached version")
            return cache_file.read_text()
        return ""


def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard. Returns True on success."""
    if platform.system() == "Darwin":
        cmd = ["pbcopy"]
    elif shutil.which("xclip"):
        cmd = ["xclip", "-selection", "clipboard"]
    elif shutil.which("xsel"):
        cmd = ["xsel", "--clipboard", "--input"]
    else:
        return False

    try:
        subprocess.run(cmd, input=text.encode(), check=True, timeout=5)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def build_ai_prompt(command_name: str, output: str, version: str) -> None:
    """Build an AI-ready diagnostic prompt and copy to clipboard."""
    docs = fetch_ai_docs(version)

    prompt_text = f"""You are a Meridian VPN proxy troubleshooting assistant.

Meridian is an Ansible-based tool for deploying censorship-resistant VLESS+Reality proxy servers.

## Reference Documentation

{docs}

## Command Output: `meridian {command_name}`

```
{output}
```

Analyze the output above and provide specific recommendations."""

    size_kb = len(prompt_text.encode()) / 1024

    if copy_to_clipboard(prompt_text):
        ok(f"AI prompt copied to clipboard ({size_kb:.1f} KB)")
        info("Paste into ChatGPT, Claude, or any AI assistant for analysis")
    else:
        info(f"AI prompt ({size_kb:.1f} KB) — copy the text below:")
        print(prompt_text)
