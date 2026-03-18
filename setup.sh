#!/usr/bin/env bash
# =============================================================================
# One-command proxy server setup
#
# Usage:
#   curl -sS https://raw.githubusercontent.com/uburuntu/meridian/main/setup.sh | bash
#   curl -sS https://raw.githubusercontent.com/uburuntu/meridian/main/setup.sh | bash -s -- 1.2.3.4
#   curl -sS https://raw.githubusercontent.com/uburuntu/meridian/main/setup.sh | bash -s -- 1.2.3.4 --domain example.com
# =============================================================================
set -euo pipefail

ORIG_PWD="${PWD}"

# --- Colors ---
R='\033[0m' B='\033[1m' D='\033[2m'
G='\033[32m' Y='\033[33m' C='\033[36m' RED='\033[31m'

info()  { printf "${C}→${R} %s\n" "$*"; }
ok()    { printf "${G}✓${R} %s\n" "$*"; }
warn()  { printf "${Y}!${R} %s\n" "$*"; }
fail()  { printf "${RED}✗ %s${R}\n" "$*" >&2; exit 1; }
ask()   { printf "${B}?${R} %s: " "$*"; }

# --- Parse args ---
SERVER_IP=""
DOMAIN=""
EMAIL=""
EXTRA_ARGS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --email)  EMAIL="$2"; shift 2 ;;
    --chain)  EXTRA_ARGS="chain"; shift ;;
    -*)       fail "Unknown flag: $1" ;;
    *)        SERVER_IP="$1"; shift ;;
  esac
done

printf "\n${B}Meridian${R} — Proxy Server Setup\n\n"

# --- Prompt for IP if not given ---
if [[ -z "$SERVER_IP" ]]; then
  ask "Server IP address"
  read -r SERVER_IP
  [[ -z "$SERVER_IP" ]] && fail "Server IP is required"
fi
printf "\n"

# --- Detect OS ---
OS="unknown"
if [[ "$OSTYPE" == "darwin"* ]]; then
  OS="mac"
elif [[ "$OSTYPE" == "linux"* ]]; then
  OS="linux"
else
  warn "Unknown OS: $OSTYPE — assuming Linux"
  OS="linux"
fi

# --- Validate IP format ---
if ! [[ "$SERVER_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  fail "Invalid IP address: $SERVER_IP
  Expected format: 123.45.67.89"
fi

# --- Check SSH access ---
ANSIBLE_USER="${ANSIBLE_USER:-root}"
info "Checking SSH access to ${ANSIBLE_USER}@${SERVER_IP}..."
if ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new "${ANSIBLE_USER}@${SERVER_IP}" true 2>/dev/null; then
  ok "SSH connection successful"
else
  fail "Cannot SSH to ${ANSIBLE_USER}@${SERVER_IP}

  Possible fixes:
  1. Copy your SSH key:  ssh-copy-id ${ANSIBLE_USER}@${SERVER_IP}
  2. Test manually:      ssh ${ANSIBLE_USER}@${SERVER_IP}
  3. Different user:     ANSIBLE_USER=ubuntu bash setup.sh ${SERVER_IP}"
fi

# --- Install dependencies ---
install_if_missing() {
  local cmd="$1" name="$2" install_cmd="$3"
  if command -v "$cmd" &>/dev/null; then
    ok "$name already installed"
  else
    info "Installing $name..."
    eval "$install_cmd" || fail "Failed to install $name"
    ok "$name installed"
  fi
}

if [[ "$OS" == "mac" ]]; then
  if ! command -v brew &>/dev/null; then
    warn "Homebrew not found. Install it from https://brew.sh"
    warn "Then re-run this script."
    fail "Homebrew is required on macOS"
  fi
  install_if_missing qrencode qrencode "brew install qrencode"
  install_if_missing ansible ansible "pip3 install --quiet --user ansible"
elif [[ "$OS" == "linux" ]]; then
  install_if_missing qrencode qrencode "sudo apt-get install -y -qq qrencode >/dev/null 2>&1"
  install_if_missing ansible ansible "pip3 install --quiet --user ansible"
fi

# --- Download project ---
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

info "Downloading playbook..."
if command -v curl &>/dev/null; then
  curl -sL "https://github.com/uburuntu/meridian/archive/refs/heads/main.tar.gz" | tar xz -C "$WORK_DIR" --strip-components=1
elif command -v wget &>/dev/null; then
  wget -qO- "https://github.com/uburuntu/meridian/archive/refs/heads/main.tar.gz" | tar xz -C "$WORK_DIR" --strip-components=1
else
  fail "curl or wget is required"
fi
ok "Playbook downloaded"

cd "$WORK_DIR"

# --- Install Ansible collections ---
info "Installing Ansible collections..."
ansible-galaxy collection install -r requirements.yml --quiet 2>/dev/null || \
  ansible-galaxy collection install -r requirements.yml >/dev/null 2>&1
ok "Collections ready"

# --- Write inventory ---
cat > inventory.yml <<EOF
all:
  hosts:
    proxy:
      ansible_host: "$SERVER_IP"
      ansible_user: "$ANSIBLE_USER"
EOF

# --- Build ansible-playbook command ---
PLAY_CMD="ansible-playbook playbook.yml -e server_public_ip=$SERVER_IP"
[[ -n "$DOMAIN" ]] && PLAY_CMD="$PLAY_CMD -e domain=$DOMAIN"
[[ -n "$EMAIL" ]]  && PLAY_CMD="$PLAY_CMD -e email=$EMAIL"

printf "\n"
info "Configuring server at ${B}$SERVER_IP${R}..."
[[ -n "$DOMAIN" ]] && info "Domain: $DOMAIN"
printf "\n"

# --- Run playbook ---
$PLAY_CMD

# --- Copy output files to caller's directory ---
ORIG_DIR="$ORIG_PWD"
if [[ -d credentials ]]; then
  mkdir -p "$ORIG_DIR/vpn-credentials"
  cp credentials/* "$ORIG_DIR/vpn-credentials/" 2>/dev/null || true
  printf "\n${G}${B}Done!${R}\n\n"
  printf "Credentials saved to: ${B}$ORIG_DIR/vpn-credentials/${R}\n"
  printf "Send the HTML file to your contact — they scan the QR code and connect.\n\n"
else
  printf "\n${G}${B}Done!${R} Check the output above for connection details.\n\n"
fi
