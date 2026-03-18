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
UNINSTALL=false
ANSIBLE_USER="${ANSIBLE_USER:-root}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)    DOMAIN="$2"; shift 2 ;;
    --email)     EMAIL="$2"; shift 2 ;;
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
  printf "  The server will look like ${D}microsoft.com${R} to any probe.\n"
  printf "  Takes ~2 minutes. Safe to re-run.\n"
  printf "\n"
  line
  printf "\n"
  printf "  ${B}Where is the server?${R}\n\n"

  # Auto-detect current machine's public IP as a default suggestion
  DETECTED_IP=$(curl -s --max-time 3 https://ifconfig.me </dev/null 2>/dev/null || true)

  while true; do
    prompt SERVER_IP "IP address" "$DETECTED_IP"
    if [[ "$SERVER_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      break
    fi
    printf "  ${RED}Enter a valid IP like 123.45.67.89${R}\n" > /dev/tty
  done

  prompt ANSIBLE_USER "SSH user" "root"

  printf "\n"
  printf "  ${B}Optional — decoy website + CDN fallback:${R}\n\n"
  prompt DOMAIN "Domain" "skip"
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
LOCAL_MODE=false
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
  ansible-galaxy collection install -r requirements.yml >/dev/null 2>&1 || fail "Failed to install Ansible collections"
fi
ok "Collections ready"

# --- Restore credentials from previous run (for idempotent re-runs) ---
for cred_dir in "$ORIG_PWD/meridian" "$ORIG_PWD/vpn-credentials" "$HOME/meridian"; do
  if [[ -d "$cred_dir" ]] && ls "$cred_dir"/*.yml &>/dev/null; then
    mkdir -p credentials
    cp "$cred_dir"/*.yml credentials/ 2>/dev/null || true
    ok "Loaded credentials from $cred_dir"
    break
  fi
done

# --- Write inventory ---
if [[ "$LOCAL_MODE" == true ]]; then
  cat > inventory.yml <<EOF
all:
  hosts:
    proxy:
      ansible_host: "$SERVER_IP"
      ansible_connection: local
EOF
else
  cat > inventory.yml <<EOF
all:
  hosts:
    proxy:
      ansible_host: "$SERVER_IP"
      ansible_user: "$ANSIBLE_USER"
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
PLAY_CMD="ansible-playbook playbook.yml -e server_public_ip=$SERVER_IP"
[[ -n "$DOMAIN" ]] && PLAY_CMD="$PLAY_CMD -e domain=$DOMAIN"
[[ -n "$EMAIL" ]]  && PLAY_CMD="$PLAY_CMD -e email=$EMAIL"

printf "\n"
info "Configuring server at ${B}$SERVER_IP${R}..."
[[ -n "$DOMAIN" ]] && info "Domain: $DOMAIN"
printf "\n"

$PLAY_CMD

# --- Copy output files ---
ORIG_DIR="$ORIG_PWD"
if [[ -d credentials ]]; then
  mkdir -p "$ORIG_DIR/meridian"
  cp credentials/* "$ORIG_DIR/meridian/" 2>/dev/null || true
  printf "\n  ${G}${B}Done!${R}\n\n"
  printf "  Credentials saved to: ${B}$ORIG_DIR/meridian/${R}\n"
  printf "  Send the HTML file to whoever needs it — they scan the QR code and connect.\n\n"
else
  printf "\n  ${G}${B}Done!${R} Check the output above for connection details.\n\n"
fi
