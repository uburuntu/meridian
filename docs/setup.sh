#!/usr/bin/env bash
# =============================================================================
# Meridian — Compatibility shim
#
# This script installs the `meridian` CLI and guides users to the new interface.
# The old `curl setup.sh | bash` pattern is replaced by:
#
#   curl -sSf https://meridian.msu.rocks/install.sh | bash
#   meridian setup 1.2.3.4
#
# For backward compatibility, this script still works:
#   curl -sS https://meridian.msu.rocks/setup.sh | bash
# =============================================================================
set -euo pipefail

R='\033[0m' B='\033[1m' D='\033[2m'
G='\033[32m' C='\033[36m' Y='\033[33m'

printf "\n"
printf "  ${B}Meridian${R}\n"
printf "\n"
printf "  ${Y}!${R} setup.sh has been replaced by the ${B}meridian${R} CLI.\n"
printf "\n"

# Check if meridian is already installed (and not the old bash version)
if command -v meridian &>/dev/null; then
  MERIDIAN_PATH=$(command -v meridian)
  if ! grep -q 'MERIDIAN_VERSION=' "$MERIDIAN_PATH" 2>/dev/null; then
    # It's the new Python CLI
    printf "  ${G}✓${R} meridian CLI is already installed.\n\n"
    printf "  Usage:\n"
    printf "    ${C}meridian setup${R}              ${D}# interactive wizard${R}\n"
    printf "    ${C}meridian setup 1.2.3.4${R}      ${D}# deploy to server${R}\n"
    printf "    ${C}meridian client add alice${R}    ${D}# share access${R}\n"
    printf "    ${C}meridian help${R}               ${D}# all commands${R}\n"
    printf "\n"

    # If arguments were passed, forward them to meridian
    if [[ $# -gt 0 ]]; then
      printf "  ${C}→${R} Running: meridian setup %s\n\n" "$*"
      exec meridian setup "$@"
    fi

    exit 0
  fi
fi

# Install meridian CLI (handles old bash CLI migration automatically)
printf "  Installing meridian CLI...\n\n"

INSTALL_URL="https://meridian.msu.rocks/install.sh"
FALLBACK_URL="https://raw.githubusercontent.com/uburuntu/meridian/main/install.sh"

INSTALLER=""
if command -v curl &>/dev/null; then
  INSTALLER=$(curl -sSf "$INSTALL_URL" </dev/null 2>/dev/null) || \
  INSTALLER=$(curl -sSf "$FALLBACK_URL" </dev/null 2>/dev/null) || true
elif command -v wget &>/dev/null; then
  INSTALLER=$(wget -qO- "$INSTALL_URL" </dev/null 2>/dev/null) || \
  INSTALLER=$(wget -qO- "$FALLBACK_URL" </dev/null 2>/dev/null) || true
fi

if [[ -z "$INSTALLER" ]]; then
  printf "  Failed to download installer.\n"
  printf "  Manual install: https://github.com/uburuntu/meridian#install\n\n"
  exit 1
fi

bash -c "$INSTALLER" </dev/null

# If arguments were passed, forward them to meridian
if [[ $# -gt 0 ]] && command -v meridian &>/dev/null; then
  printf "\n  ${C}→${R} Running: meridian setup %s\n\n" "$*"
  exec meridian setup "$@"
fi
