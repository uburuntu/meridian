#!/usr/bin/env bash
# =============================================================================
# Meridian CLI Installer
#
# Installs the `meridian` command to ~/.local/bin/meridian
#
# Usage:
#   curl -sSf https://meridian.msu.rocks/install.sh | bash
# =============================================================================
set -euo pipefail

R='\033[0m' B='\033[1m' D='\033[2m'
G='\033[32m' C='\033[36m' RED='\033[31m'

info()  { printf "  ${C}→${R} %s\n" "$*"; }
ok()    { printf "  ${G}✓${R} %s\n" "$*"; }
fail()  { printf "\n  ${RED}✗ %s${R}\n" "$*" >&2; exit 1; }

INSTALL_DIR="${MERIDIAN_INSTALL_DIR:-$HOME/.local/bin}"
DOWNLOAD_URL="https://meridian.msu.rocks/meridian"
FALLBACK_URL="https://raw.githubusercontent.com/uburuntu/meridian/main/meridian"

printf "\n"
printf "  ${B}Meridian Installer${R}\n"
printf "\n"

# --- Download CLI ---
info "Downloading meridian CLI..."
CLI_CONTENT=""
if command -v curl &>/dev/null; then
  CLI_CONTENT=$(curl -sSf "$DOWNLOAD_URL" </dev/null 2>/dev/null) || \
  CLI_CONTENT=$(curl -sSf "$FALLBACK_URL" </dev/null 2>/dev/null) || true
elif command -v wget &>/dev/null; then
  CLI_CONTENT=$(wget -qO- "$DOWNLOAD_URL" </dev/null 2>/dev/null) || \
  CLI_CONTENT=$(wget -qO- "$FALLBACK_URL" </dev/null 2>/dev/null) || true
else
  fail "curl or wget is required"
fi

if [[ -z "$CLI_CONTENT" ]]; then
  fail "Failed to download meridian CLI"
fi

# Validate it looks like the right script
if [[ "$CLI_CONTENT" != *"MERIDIAN_VERSION"* ]]; then
  fail "Downloaded file doesn't look like the meridian CLI"
fi

# --- Install ---
mkdir -p "$INSTALL_DIR"
printf '%s\n' "$CLI_CONTENT" > "$INSTALL_DIR/meridian"
chmod +x "$INSTALL_DIR/meridian"
ok "Installed to $INSTALL_DIR/meridian"

# --- Ensure PATH ---
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
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

  PATH_LINE="export PATH=\"$INSTALL_DIR:\$PATH\""
  PATH_ADDED=1

  if [[ -n "$PROFILE" ]]; then
    if ! grep -qF "$INSTALL_DIR" "$PROFILE" 2>/dev/null; then
      printf '\n# Meridian CLI\n%s\n' "$PATH_LINE" >> "$PROFILE"
      ok "Added $INSTALL_DIR to PATH in $PROFILE"
    fi
  fi

  export PATH="$INSTALL_DIR:$PATH"
fi

# --- Extract version ---
INSTALLED_VERSION=$(grep '^MERIDIAN_VERSION=' "$INSTALL_DIR/meridian" 2>/dev/null | head -1 | cut -d'"' -f2)

printf "\n"
printf "  ${G}${B}Meridian ${INSTALLED_VERSION:-CLI} installed.${R}\n\n"

if [[ "${PATH_ADDED:-}" == "1" ]]; then
  PROFILE_NAME=$(basename "${PROFILE:-~/.bashrc}")
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
