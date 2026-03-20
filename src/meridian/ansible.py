"""Ansible playbook execution and dependency management."""

from __future__ import annotations

import os
import shutil
import subprocess
from importlib.resources import files as pkg_files
from pathlib import Path

from meridian.config import MERIDIAN_HOME, is_macos
from meridian.console import fail, info, ok, warn


def _extend_path_for_pip_user() -> None:
    """Add pip --user bin directories to PATH so newly installed tools are found."""
    import glob
    import sys

    dirs_to_add = [
        os.path.expanduser("~/.local/bin"),  # Linux
    ]
    if is_macos():
        # macOS pip3 --user installs to ~/Library/Python/X.Y/bin
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        dirs_to_add.append(os.path.expanduser(f"~/Library/Python/{py_ver}/bin"))
        # Also check glob pattern for other versions
        for d in glob.glob(os.path.expanduser("~/Library/Python/*/bin")):
            dirs_to_add.append(d)

    current_path = os.environ.get("PATH", "")
    for d in dirs_to_add:
        if os.path.isdir(d) and d not in current_path:
            os.environ["PATH"] = d + os.pathsep + current_path
            current_path = os.environ["PATH"]


def get_playbooks_dir() -> Path:
    """Return path to bundled playbooks via importlib.resources."""
    playbooks = pkg_files("meridian") / "playbooks"
    return Path(str(playbooks))


def write_inventory(ip: str, user: str, local_mode: bool) -> Path:
    """Generate inventory.yml in ~/.meridian/ (not inside package dir)."""
    inv_path = MERIDIAN_HOME / "inventory.yml"
    MERIDIAN_HOME.mkdir(parents=True, exist_ok=True)

    lines = ["---", "all:", "  hosts:", "    proxy:"]
    if local_mode:
        lines.append("      ansible_connection: local")
    else:
        lines.append(f"      ansible_host: {ip}")
        lines.append(f"      ansible_user: {user}")
    if user != "root":
        lines.append("      ansible_become: true")

    inv_path.write_text("\n".join(lines) + "\n")
    return inv_path


def ensure_qrencode() -> None:
    """Warn if qrencode is not installed (needed for QR code generation)."""
    if shutil.which("qrencode"):
        return
    warn("qrencode not found — QR codes will not be generated")
    info("Install it: brew install qrencode (macOS) or apt install qrencode (Linux)")


def ensure_ansible() -> None:
    """Ensure ansible-playbook is available in PATH."""
    if shutil.which("ansible-playbook"):
        return

    # Maybe it's installed but not on PATH (pip --user)
    _extend_path_for_pip_user()
    if shutil.which("ansible-playbook"):
        return

    info("Installing Ansible...")

    # Try pipx first
    if shutil.which("pipx"):
        result = subprocess.run(
            ["pipx", "install", "ansible", "--quiet"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            ok("Ansible installed via pipx")
            return

    # Try pip3 --user
    if shutil.which("pip3"):
        result = subprocess.run(
            ["pip3", "install", "--user", "ansible"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            _extend_path_for_pip_user()
            ok("Ansible installed via pip3")
            return

        # PEP 668 fallback
        result = subprocess.run(
            ["pip3", "install", "--user", "--break-system-packages", "ansible"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            _extend_path_for_pip_user()
            ok("Ansible installed via pip3")
            return

    # Try apt
    if shutil.which("apt-get"):
        result = subprocess.run(
            ["sudo", "apt-get", "install", "-y", "ansible"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            ok("Ansible installed via apt")
            return

    if shutil.which("apt"):
        result = subprocess.run(
            ["sudo", "apt", "install", "-y", "ansible"],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            ok("Ansible installed via apt")
            return

    fail("Could not install Ansible. Please install it manually: pip3 install ansible")


def ensure_collections(playbooks_dir: Path) -> None:
    """Install Ansible Galaxy collections from requirements.yml with retry."""
    req_file = playbooks_dir / "requirements.yml"
    if not req_file.exists():
        return

    for attempt in range(1, 4):
        result = subprocess.run(
            ["ansible-galaxy", "collection", "install", "-r", str(req_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return
        if attempt < 3:
            warn(f"Collection install attempt {attempt}/3 failed, retrying...")

    # Final attempt — show output for debugging
    subprocess.run(
        ["ansible-galaxy", "collection", "install", "-r", str(req_file)],
    )


def run_playbook(
    playbook: str,
    ip: str,
    creds_dir: Path,
    extra_vars: dict[str, str] | None = None,
    local_mode: bool = False,
    user: str = "root",
) -> int:
    """Execute ansible-playbook with standard Meridian arguments."""
    playbooks_dir = get_playbooks_dir()
    inv_path = write_inventory(ip, user, local_mode)

    cmd = [
        "ansible-playbook",
        "-i",
        str(inv_path),
        str(playbooks_dir / playbook),
        "-e",
        f"server_public_ip={ip}",
        "-e",
        f"credentials_dir={creds_dir}",
    ]
    for k, v in (extra_vars or {}).items():
        cmd.extend(["-e", f"{k}={v}"])

    env = os.environ.copy()
    env["ANSIBLE_CONFIG"] = str(playbooks_dir / "ansible.cfg")
    # Work around /dev/shm errors on macOS (no shared memory support)
    if is_macos():
        env["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

    result = subprocess.run(cmd, cwd=str(playbooks_dir), env=env)
    return result.returncode
