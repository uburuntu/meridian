#!/usr/bin/env bash
# =============================================================================
# Meridian — One-command proxy server setup
#
# Interactive:  curl -sS https://raw.githubusercontent.com/uburuntu/meridian/main/setup.sh | bash
# With flags:   curl -sS ... | bash -s -- 1.2.3.4 --domain example.com
# Uninstall:    curl -sS ... | bash -s -- --uninstall
# =============================================================================
set -euo pipefail

ORIG_PWD="${PWD}"

# --- Colors & output helpers ---
R='\033[0m' B='\033[1m' D='\033[2m'
G='\033[32m' Y='\033[33m' C='\033[36m' RED='\033[31m'

info()  { printf "  ${C}→${R} %s\n" "$*"; }
ok()    { printf "  ${G}✓${R} %s\n" "$*"; }
warn()  { printf "  ${Y}!${R} %s\n" "$*"; }
fail()  { printf "\n  ${RED}✗ %s${R}\n\n" "$*" >&2; exit 1; }
line()  { printf "  ${D}─────────────────────────────────────────${R}\n"; }

# Read from /dev/tty so it works in curl | bash
prompt() {
  local varname="$1" message="$2" default="${3:-}"
  printf "  ${B}%s${R}" "$message" > /dev/tty
  [[ -n "$default" ]] && printf " ${D}[%s]${R}" "$default" > /dev/tty
  printf ": " > /dev/tty
  local value
  read -r value < /dev/tty || true
  [[ -z "$value" && -n "$default" ]] && value="$default"
  eval "$varname=\$value"
}

confirm() {
  printf "\n  Press ${B}Enter${R} to start, or ${D}Ctrl+C${R} to cancel. " > /dev/tty
  read -r < /dev/tty || true
}

# --- Parse args ---
SERVER_IP=""
DOMAIN=""
EMAIL=""
SNI=""
UNINSTALL=false
LOCAL_MODE=false
ANSIBLE_USER="${ANSIBLE_USER:-root}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)    DOMAIN="$2"; shift 2 ;;
    --email)     EMAIL="$2"; shift 2 ;;
    --sni)       SNI="$2"; shift 2 ;;
    --user)      ANSIBLE_USER="$2"; shift 2 ;;
    --uninstall) UNINSTALL=true; shift ;;
    --help|-h)
      printf "\n  ${B}Meridian${R} — Proxy Server Setup\n\n"
      printf "  Usage:\n"
      printf "    curl -sS https://...setup.sh | bash              ${D}# interactive wizard${R}\n"
      printf "    curl -sS ... | bash -s -- IP                     ${D}# with server IP${R}\n"
      printf "    curl -sS ... | bash -s -- IP --domain example.com\n"
      printf "    curl -sS ... | bash -s -- --uninstall\n\n"
      printf "  Flags:\n"
      printf "    --domain DOMAIN   Add decoy website + CDN fallback\n"
      printf "    --sni HOST        Reality camouflage target (default: www.microsoft.com)\n"
      printf "    --user USER       SSH user (default: root)\n"
      printf "    --uninstall       Remove proxy from server\n"
      printf "    --help            Show this help\n\n"
      exit 0 ;;
    -*)          fail "Unknown flag: $1. Use --help for usage." ;;
    *)           SERVER_IP="$1"; shift ;;
  esac
done

# --- Detect OS ---
OS="unknown"
if [[ "$OSTYPE" == "darwin"* ]]; then
  OS="mac"
elif [[ "$OSTYPE" == "linux"* ]]; then
  OS="linux"
else
  OS="linux"
fi

# --- Welcome banner ---
printf "\n"
printf "  ${B}Meridian${R}\n"
printf "\n"

# --- Interactive mode (no args) ---
if [[ -z "$SERVER_IP" && "$UNINSTALL" != true ]]; then
  printf "  Deploy a censorship-resistant proxy server.\n"
  printf "  The server will look like ${D}${SNI:-www.microsoft.com}${R} to any probe.\n"
  printf "  Takes ~2 minutes. Safe to re-run.\n"
  printf "\n"
  line
  printf "\n"
  printf "  ${B}Where is the server?${R}\n\n"

  # Auto-detect public IPv4 (force -4 to avoid IPv6)
  DETECTED_IP=$(curl -4 -s --max-time 3 https://ifconfig.me </dev/null 2>/dev/null || \
                curl -4 -s --max-time 3 https://api.ipify.org </dev/null 2>/dev/null || \
                curl -s --max-time 3 https://ifconfig.me </dev/null 2>/dev/null || true)
  # Strip any non-IPv4 result
  if ! [[ "$DETECTED_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    DETECTED_IP=""
  fi

  while true; do
    prompt SERVER_IP "IP address" "$DETECTED_IP"
    if [[ "$SERVER_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      break
    fi
    printf "  ${RED}Enter a valid IPv4 address (e.g. 123.45.67.89)${R}\n" > /dev/tty
  done

  prompt ANSIBLE_USER "SSH user" "root"
  if [[ "$ANSIBLE_USER" != "root" ]]; then
    printf "  ${D}(sudo will be used for privileged operations)${R}\n" > /dev/tty
  fi

  printf "\n"
  printf "  ${B}Optional — decoy website + CDN fallback:${R}\n\n"

  # Try to detect a domain already configured on this server:
  # 1. Check saved credentials from previous run
  # 2. Check Caddy config on the server (if accessible via SSH)
  # 3. Fall back to reverse DNS
  SUGGESTED_DOMAIN=""

  # Check local credentials for a previously used domain
  for cred_dir in "$ORIG_PWD/meridian" "$HOME/meridian"; do
    if [[ -f "$cred_dir/proxy.yml" ]]; then
      PREV_DOMAIN=$(grep '^domain:' "$cred_dir/proxy.yml" 2>/dev/null | awk '{print $2}' | tr -d '"' || true)
      if [[ -n "$PREV_DOMAIN" ]]; then
        SUGGESTED_DOMAIN="$PREV_DOMAIN"
        break
      fi
    fi
  done

  # Check Caddy config on the server (works in local mode or via SSH)
  if [[ -z "$SUGGESTED_DOMAIN" ]]; then
    CADDY_DOMAIN=""
    if [[ "$LOCAL_MODE" == true ]]; then
      CADDY_DOMAIN=$(grep -oE '^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-z]{2,}' /etc/caddy/Caddyfile 2>/dev/null | head -1 || true)
    else
      CADDY_DOMAIN=$(ssh -o BatchMode=yes -o ConnectTimeout=3 "${ANSIBLE_USER}@${SERVER_IP}" \
        "grep -oE '^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-z]{2,}' /etc/caddy/Caddyfile 2>/dev/null | head -1" </dev/null 2>/dev/null || true)
    fi
    if [[ -n "$CADDY_DOMAIN" ]]; then
      SUGGESTED_DOMAIN="$CADDY_DOMAIN"
    fi
  fi

  # Fall back to reverse DNS
  if [[ -z "$SUGGESTED_DOMAIN" ]]; then
    if command -v dig &>/dev/null; then
      REVERSE_DNS=$(dig -x "$SERVER_IP" +short </dev/null 2>/dev/null | head -1 | sed 's/\.$//')
      if [[ -n "$REVERSE_DNS" && "$REVERSE_DNS" != *"in-addr"* ]]; then
        SUGGESTED_DOMAIN="$REVERSE_DNS"
      fi
    fi
  fi

  if [[ -n "$SUGGESTED_DOMAIN" ]]; then
    printf "  ${D}Detected: ${SUGGESTED_DOMAIN}${R}\n" > /dev/tty
  fi
  prompt DOMAIN "Domain" "${SUGGESTED_DOMAIN:-skip}"
  [[ "$DOMAIN" == "skip" || "$DOMAIN" == "" ]] && DOMAIN=""

  printf "\n"
  line
  printf "\n"
  printf "  ${B}Summary${R}\n\n"
  printf "  Target:  ${G}${ANSIBLE_USER}@${SERVER_IP}${R}\n"
  if [[ -n "$DOMAIN" ]]; then
    printf "  Domain:  ${G}${DOMAIN}${R}\n"
    printf "  Mode:    Reality + CDN fallback + decoy site\n"
  else
    printf "  Domain:  ${D}(none)${R}\n"
    printf "  Mode:    Standalone (Reality only)\n"
  fi
  printf "\n"
  line

  confirm
  printf "\n"
fi

# --- Validate IP ---
if [[ "$UNINSTALL" != true ]]; then
  if [[ -z "$SERVER_IP" ]]; then
    fail "Server IP is required. Run without flags for interactive mode."
  fi
  if ! [[ "$SERVER_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    fail "Invalid IP address: $SERVER_IP\n  Expected format: 123.45.67.89"
  fi
fi

# --- Handle uninstall ---
if [[ "$UNINSTALL" == true ]]; then
  if [[ -z "$SERVER_IP" ]]; then
    CRED_FILE=$(ls "$ORIG_PWD"/meridian/*.yml 2>/dev/null | head -1)
    if [[ -n "$CRED_FILE" ]]; then
      SAVED_IP=$(grep 'exit_ip:' "$CRED_FILE" 2>/dev/null | awk '{print $2}' | tr -d '"')
      [[ -n "$SAVED_IP" ]] && SERVER_IP="$SAVED_IP" && info "Found server: $SERVER_IP"
    fi
  fi
  if [[ -z "$SERVER_IP" ]]; then
    prompt SERVER_IP "Server IP to uninstall from"
    [[ -z "$SERVER_IP" ]] && fail "Server IP is required for uninstall"
  fi

  printf "\n"
  warn "This will remove Meridian from $SERVER_IP."
  warn "Docker and system packages will NOT be touched."
  printf "\n"
  prompt CONFIRM "Continue? (y/N)"
  [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]] && { info "Cancelled."; exit 0; }
  printf "\n"
fi

# --- Detect if we're running on the target server itself ---
LOCAL_IP=$(curl -s --max-time 3 https://ifconfig.me </dev/null 2>/dev/null || true)
if [[ "$LOCAL_IP" == "$SERVER_IP" ]]; then
  LOCAL_MODE=true
  ok "Running on the target server (local mode)"
else
  # Check SSH access (only needed when deploying remotely)
  info "Checking SSH access to ${ANSIBLE_USER}@${SERVER_IP}..."
  if ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new "${ANSIBLE_USER}@${SERVER_IP}" true </dev/null 2>/dev/null; then
    ok "SSH connection successful"
  else
    printf "\n"
    fail "Cannot SSH to ${ANSIBLE_USER}@${SERVER_IP}

  Possible fixes:
  1. Copy your SSH key:  ssh-copy-id ${ANSIBLE_USER}@${SERVER_IP}
  2. Test manually:      ssh ${ANSIBLE_USER}@${SERVER_IP}
  3. Different user:     pass --user ubuntu"
  fi
fi

# --- Install dependencies ---
install_if_missing() {
  local cmd="$1" name="$2" install_cmd="$3"
  if command -v "$cmd" &>/dev/null; then
    ok "$name already installed"
    return 0
  fi
  info "Installing $name..."
  if eval "$install_cmd"; then
    ok "$name installed"
  else
    fail "Failed to install $name"
  fi
}

install_ansible() {
  # Try multiple install methods — first success wins.
  # Each attempt is guarded so set -e doesn't kill the script on failure.
  if command -v pipx &>/dev/null; then
    if pipx install ansible --quiet 2>/dev/null; then return 0; fi
  fi
  if command -v pip3 &>/dev/null; then
    if pip3 install --quiet --user ansible 2>/dev/null; then return 0; fi
    if pip3 install --quiet --user --break-system-packages ansible 2>/dev/null; then return 0; fi
  fi
  if [[ "$OS" == "linux" ]]; then
    if sudo apt-get install -y -qq ansible >/dev/null 2>&1; then return 0; fi
  fi
  return 1
}

if [[ "$OS" == "mac" ]]; then
  if ! command -v brew &>/dev/null; then
    fail "Homebrew not found. Install it from https://brew.sh then re-run."
  fi
  install_if_missing qrencode qrencode "brew install qrencode"
  install_if_missing ansible ansible "install_ansible"
elif [[ "$OS" == "linux" ]]; then
  install_if_missing qrencode qrencode "sudo apt-get install -y -qq qrencode >/dev/null 2>&1"
  install_if_missing ansible ansible "install_ansible"
fi

# Ensure pip --user bin directories are in PATH (pip3 install --user puts binaries there)
for p in "$HOME/.local/bin" "$HOME/Library/Python"/*/bin; do
  [[ -d "$p" ]] && [[ ":$PATH:" != *":$p:"* ]] && export PATH="$p:$PATH"
done

# --- Download project ---
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

info "Downloading playbook..."
if command -v curl &>/dev/null; then
  curl -sL "https://github.com/uburuntu/meridian/archive/refs/heads/main.tar.gz" </dev/null | tar xz -C "$WORK_DIR" --strip-components=1
elif command -v wget &>/dev/null; then
  wget -qO- "https://github.com/uburuntu/meridian/archive/refs/heads/main.tar.gz" </dev/null | tar xz -C "$WORK_DIR" --strip-components=1
else
  fail "curl or wget is required"
fi
ok "Playbook downloaded"

cd "$WORK_DIR"

# --- Install Ansible collections ---
info "Installing Ansible collections..."
if ! ansible-galaxy collection install -r requirements.yml --quiet 2>/dev/null; then
  # Retry without suppressing output so the user can see what went wrong
  ansible-galaxy collection install -r requirements.yml || fail "Failed to install Ansible collections"
fi
ok "Collections ready"

# --- Restore credentials from previous run (for idempotent re-runs) ---
# Search common locations + orphaned temp dirs from failed runs
CRED_FOUND=false
for cred_dir in "$ORIG_PWD/meridian" "$HOME/meridian" "$ORIG_PWD/vpn-credentials"; do
  if [[ -d "$cred_dir" ]] && ls "$cred_dir"/*.yml &>/dev/null; then
    mkdir -p credentials
    cp "$cred_dir"/*.yml credentials/ 2>/dev/null || true
    ok "Loaded credentials from $cred_dir"
    CRED_FOUND=true
    break
  fi
done
# Also check /tmp for orphaned credentials from failed setup.sh runs
if [[ "$CRED_FOUND" != true ]]; then
  ORPHAN=$(find /tmp -maxdepth 3 -name "proxy.yml" -path "*/credentials/*" 2>/dev/null | head -1)
  if [[ -n "$ORPHAN" ]]; then
    mkdir -p credentials
    cp "$(dirname "$ORPHAN")"/*.yml credentials/ 2>/dev/null || true
    ok "Recovered credentials from previous run"
  fi
fi

# --- Write inventory ---
BECOME_LINE=""
if [[ "$ANSIBLE_USER" != "root" ]]; then
  BECOME_LINE="      ansible_become: true"
fi

if [[ "$LOCAL_MODE" == true ]]; then
  cat > inventory.yml <<EOF
all:
  hosts:
    proxy:
      ansible_host: "$SERVER_IP"
      ansible_connection: local
${BECOME_LINE}
EOF
else
  cat > inventory.yml <<EOF
all:
  hosts:
    proxy:
      ansible_host: "$SERVER_IP"
      ansible_user: "$ANSIBLE_USER"
${BECOME_LINE}
EOF
fi

# --- Run uninstall if requested ---
if [[ "$UNINSTALL" == true ]]; then
  info "Removing Meridian from $SERVER_IP..."
  printf "\n"
  ansible-playbook playbook-uninstall.yml
  printf "\n  ${G}${B}Uninstall complete.${R}\n\n"
  exit 0
fi

# --- Build and run playbook ---
# Point credentials to a stable location (survives temp dir cleanup)
STABLE_CREDS="$HOME/meridian"
mkdir -p "$STABLE_CREDS"
PLAY_CMD="ansible-playbook playbook.yml -e server_public_ip=$SERVER_IP -e credentials_dir=$STABLE_CREDS"
[[ -n "$DOMAIN" ]] && PLAY_CMD="$PLAY_CMD -e domain=$DOMAIN"
[[ -n "$EMAIL" ]]  && PLAY_CMD="$PLAY_CMD -e email=$EMAIL"
[[ -n "$SNI" ]]    && PLAY_CMD="$PLAY_CMD -e reality_sni=$SNI"

printf "\n"
info "Configuring server at $SERVER_IP..."
[[ -n "$DOMAIN" ]] && info "Domain: $DOMAIN"
printf "\n"

$PLAY_CMD

# --- Done ---
printf "\n  ${G}${B}Done!${R}\n\n"
printf "  Credentials saved to: ${B}$STABLE_CREDS/${R}\n"
printf "  Send the HTML file to whoever needs it — they scan the QR code and connect.\n\n"
