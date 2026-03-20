#!/usr/bin/env bash
# =============================================================================
# Meridian CLI Installer
#
# Installs `meridian` from PyPI via uv (preferred) or pipx (fallback).
# Detects and migrates old bash CLI installations automatically.
#
# Usage:
#   curl -sSf https://meridian.msu.rocks/install.sh | bash
# =============================================================================
set -euo pipefail

R='\033[0m' B='\033[1m' D='\033[2m'
G='\033[32m' C='\033[36m' Y='\033[33m' RED='\033[31m'

info()  { printf "  ${C}→${R} %s\n" "$*"; }
ok()    { printf "  ${G}✓${R} %s\n" "$*"; }
warn()  { printf "  ${Y}!${R} %s\n" "$*"; }
fail()  { printf "\n  ${RED}✗ %s${R}\n" "$*" >&2; exit 1; }

PYPI_PACKAGE="meridian-vpn"

printf "\n"
printf "  ${B}Meridian Installer${R}\n"
printf "\n"

# =============================================================================
# Detect and migrate old bash CLI
# =============================================================================
OLD_MERIDIAN=$(command -v meridian 2>/dev/null || true)
if [[ -n "$OLD_MERIDIAN" ]] && grep -q 'MERIDIAN_VERSION=' "$OLD_MERIDIAN" 2>/dev/null; then
  warn "Found old bash CLI at $OLD_MERIDIAN"
  info "Migrating to Python package..."
  rm -f "$OLD_MERIDIAN"
  # Clean up old playbook cache (now bundled in package)
  rm -rf "$HOME/.meridian/playbooks"
  # Credentials, servers, and cache are preserved (compatible format)
  ok "Old CLI removed (credentials preserved)"
fi

# =============================================================================
# Install uv if not present
# =============================================================================
install_uv() {
  info "Installing uv (Python package manager)..."
  if command -v curl &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh </dev/null 2>/dev/null | bash 2>/dev/null
  elif command -v wget &>/dev/null; then
    wget -qO- https://astral.sh/uv/install.sh </dev/null 2>/dev/null | bash 2>/dev/null
  else
    return 1
  fi
  # Source uv's env to get it on PATH
  # shellcheck disable=SC1091
  [[ -f "$HOME/.local/bin/env" ]] && source "$HOME/.local/bin/env" 2>/dev/null || true
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
}

# =============================================================================
# Install meridian-vpn from PyPI
# =============================================================================
INSTALLED=false

# Strategy 1: uv tool install (preferred — fastest, manages Python)
if command -v uv &>/dev/null || install_uv; then
  if command -v uv &>/dev/null; then
    info "Installing meridian via uv..."
    if uv tool install "$PYPI_PACKAGE" </dev/null 2>&1; then
      INSTALLED=true
      ok "Installed via uv"
    fi
  fi
fi

# Strategy 2: pipx (fallback — available via apt/brew on many systems)
if [[ "$INSTALLED" != true ]] && command -v pipx &>/dev/null; then
  info "Installing meridian via pipx..."
  if pipx install "$PYPI_PACKAGE" </dev/null 2>&1; then
    INSTALLED=true
    ok "Installed via pipx"
  fi
fi

# Strategy 3: pip3 --user (last resort)
if [[ "$INSTALLED" != true ]] && command -v pip3 &>/dev/null; then
  info "Installing meridian via pip3..."
  if pip3 install --user "$PYPI_PACKAGE" </dev/null 2>&1; then
    INSTALLED=true
    ok "Installed via pip3"
  elif pip3 install --user --break-system-packages "$PYPI_PACKAGE" </dev/null 2>&1; then
    INSTALLED=true
    ok "Installed via pip3"
  fi
fi

if [[ "$INSTALLED" != true ]]; then
  fail "Could not install meridian. Please install uv first: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

# =============================================================================
# Ensure PATH includes tool bin directories
# =============================================================================
ensure_path() {
  local dir="$1"
  if [[ ":$PATH:" != *":$dir:"* ]] && [[ -d "$dir" ]]; then
    SHELL_NAME=$(basename "${SHELL:-/bin/bash}")
    PROFILE=""
    case "$SHELL_NAME" in
      zsh)  PROFILE="$HOME/.zshrc" ;;
      bash)
        if [[ -f "$HOME/.bashrc" ]]; then
          PROFILE="$HOME/.bashrc"
        elif [[ -f "$HOME/.bash_profile" ]]; then
          PROFILE="$HOME/.bash_profile"
        fi ;;
    esac

    if [[ -n "$PROFILE" ]] && ! grep -qF "$dir" "$PROFILE" 2>/dev/null; then
      printf '\n# Meridian CLI\nexport PATH="%s:$PATH"\n' "$dir" >> "$PROFILE"
      ok "Added $dir to PATH in $PROFILE"
      PATH_ADDED=1
    fi
    export PATH="$dir:$PATH"
  fi
}

PATH_ADDED=0
ensure_path "$HOME/.local/bin"
# macOS pip3 --user installs to ~/Library/Python/*/bin
for pybin in "$HOME"/Library/Python/*/bin; do
  [[ -d "$pybin" ]] && ensure_path "$pybin"
done

# =============================================================================
# Verify and show success
# =============================================================================
INSTALLED_VERSION=""
if command -v meridian &>/dev/null; then
  INSTALLED_VERSION=$(meridian version 2>/dev/null | awk '{print $2}' || true)
fi

printf "\n"
printf "  ${G}${B}Meridian ${INSTALLED_VERSION:-CLI} installed.${R}\n\n"

if [[ "$PATH_ADDED" == "1" ]]; then
  PROFILE_NAME=$(basename "${PROFILE:-shell config}")
  printf "  ${D}To start using meridian, run:${R}\n\n"
  printf "     ${C}source ~/${PROFILE_NAME}${R}\n\n"
  printf "  ${D}Then:${R}\n"
else
  printf "  Get started:\n"
fi
printf "     ${C}meridian setup${R}              ${D}# interactive wizard${R}\n"
printf "     ${C}meridian setup 1.2.3.4${R}      ${D}# deploy to server${R}\n"
printf "     ${C}meridian help${R}               ${D}# all commands${R}\n"
printf "\n"
