#!/usr/bin/env bash
# =============================================================================
# Meridian — One-command proxy server setup
#
# Interactive:  curl -sS https://meridian.msu.rocks/setup.sh | bash
# With flags:   curl -sS https://meridian.msu.rocks/setup.sh | bash -s -- 1.2.3.4 --domain example.com
# Uninstall:    curl -sS https://meridian.msu.rocks/setup.sh | bash -s -- --uninstall
# =============================================================================
set -euo pipefail

ORIG_PWD="${PWD}"

# --- Colors & output helpers ---
R='\033[0m' B='\033[1m' D='\033[2m'
G='\033[32m' Y='\033[33m' C='\033[36m' RED='\033[31m'

info()  { printf "  ${C}→${R} %s\n" "$*"; }
ok()    { printf "  ${G}✓${R} %s\n" "$*"; }
warn()  { printf "  ${Y}!${R} %s\n" "$*"; }
fail()  { printf "\n  ${RED}✗ %s${R}\n" "$*" >&2; printf "  ${D}Need help? Run with --rage and open an issue: https://github.com/uburuntu/meridian/issues${R}\n\n" >&2; exit 1; }
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
DIAGNOSTICS=false
CHECK=false
YES=false
LOCAL_MODE=false
ANSIBLE_USER="${ANSIBLE_USER:-root}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)    DOMAIN="$2"; shift 2 ;;
    --email)     EMAIL="$2"; shift 2 ;;
    --sni)       SNI="$2"; shift 2 ;;
    --user)      ANSIBLE_USER="$2"; shift 2 ;;
    --uninstall) UNINSTALL=true; shift ;;
    --rage|--diagnostics) DIAGNOSTICS=true; shift ;;
    --check|--preflight)  CHECK=true; shift ;;
    --yes|-y)    YES=true; shift ;;
    --help|-h)
      printf "\n  ${B}Meridian${R} — Proxy Server Setup\n\n"
      printf "  Usage:\n"
      printf "    curl -sS https://...setup.sh | bash              ${D}# interactive wizard${R}\n"
      printf "    curl -sS https://meridian.msu.rocks/setup.sh | bash -s -- IP\n"
      printf "    curl -sS https://meridian.msu.rocks/setup.sh | bash -s -- IP --domain example.com\n"
      printf "    curl -sS https://meridian.msu.rocks/setup.sh | bash -s -- --uninstall\n\n"
      printf "  Flags:\n"
      printf "    --domain DOMAIN   Add decoy website + CDN fallback\n"
      printf "    --sni HOST        Reality camouflage target (default: www.microsoft.com)\n"
      printf "    --user USER       SSH user (default: root)\n"
      printf "    --uninstall       Remove proxy from server\n"
      printf "    --check           Pre-flight check (SNI reachability, ports, blocklists)\n"
      printf "    --rage            Collect diagnostics for bug reports (no secrets)\n"
      printf "    --yes, -y         Skip confirmation prompts\n"
      printf "    --help            Show this help\n\n"
      printf "  Issues & feedback:\n"
      printf "    https://github.com/uburuntu/meridian/issues\n\n"
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
  printf "  Deploy a VLESS+Reality proxy server.\n"
  printf "  Invisible to DPI, active probing, and TLS fingerprinting.\n"
  printf "  Your server will impersonate ${D}${SNI:-www.microsoft.com}${R} — probes\n"
  printf "  get a real TLS certificate back. Takes ~2 minutes. Safe to re-run.\n"
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
      CADDY_DOMAIN=$(grep -ohE '^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-z]{2,}' /etc/caddy/conf.d/meridian.caddy /etc/caddy/Caddyfile 2>/dev/null | head -1 || true)
    else
      CADDY_DOMAIN=$(ssh -o BatchMode=yes -o ConnectTimeout=3 "${ANSIBLE_USER}@${SERVER_IP}" \
        "grep -ohE '^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-z]{2,}' /etc/caddy/conf.d/meridian.caddy /etc/caddy/Caddyfile 2>/dev/null | head -1" </dev/null 2>/dev/null || true)
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
  printf "  ${B}What will happen:${R}\n\n"
  printf "  ${D}1.${R} Install Docker and deploy ${B}Xray${R} (VLESS+Reality proxy)\n"
  printf "  ${D}2.${R} Generate unique encryption keys and credentials\n"
  printf "  ${D}3.${R} Configure firewall (UFW), enable ${B}BBR${R} congestion control\n"
  if [[ -n "$DOMAIN" ]]; then
    printf "  ${D}4.${R} Set up ${B}HAProxy${R} (SNI routing) + ${B}Caddy${R} (TLS + decoy site)\n"
    printf "  ${D}5.${R} Add VLESS+WSS inbound for CDN fallback through Cloudflare\n"
    printf "  ${D}6.${R} Output QR codes + save connection files\n"
  else
    printf "  ${D}4.${R} Output QR codes + save connection files\n"
  fi
  printf "\n"
  printf "  ${D}Your server will respond to probes with a real TLS certificate\n"
  printf "  from ${SNI:-www.microsoft.com} — indistinguishable from the genuine site.${R}\n"
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
  if [[ "$YES" != true ]]; then
    prompt CONFIRM "Continue? (y/N)"
    [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]] && { info "Cancelled."; exit 0; }
  fi
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

# Helper to run command locally or via SSH
run_on_server() {
  if [[ "$LOCAL_MODE" == true ]]; then
    bash -c "$1" 2>&1
  else
    ssh -o BatchMode=yes -o ConnectTimeout=5 "${ANSIBLE_USER}@${SERVER_IP}" "$1" </dev/null 2>&1
  fi
}

# --- Pre-flight check ---
if [[ "$CHECK" == true ]]; then
  printf "\n"
  printf "  ${B}Pre-flight Check${R}\n"
  printf "  ${D}Testing if this server can run a Reality proxy${R}\n"
  printf "\n"

  ISSUES=0
  SNI_HOST="${SNI:-www.microsoft.com}"

  # 1. Check SNI target is reachable from server (TCP connection to port 443)
  info "Checking SNI target ($SNI_HOST) reachability from server..."
  SNI_CHECK=$(run_on_server "timeout 5 bash -c 'echo | openssl s_client -connect $SNI_HOST:443 -servername $SNI_HOST 2>/dev/null | head -1'" || true)
  if [[ -z "$SNI_CHECK" ]]; then
    # Fallback: simple TCP check
    SNI_CHECK=$(run_on_server "timeout 3 bash -c 'echo >/dev/tcp/$SNI_HOST/443' 2>&1 && echo OK" || true)
  fi
  if [[ "$SNI_CHECK" == *"CONNECTED"* || "$SNI_CHECK" == *"OK"* || "$SNI_CHECK" == *"Certificate"* ]]; then
    ok "$SNI_HOST is reachable from server"
  else
    warn "$SNI_HOST is NOT reachable from server"
    warn "  Reality needs the SNI target to be accessible. Try --sni with a different site."
    warn "  Good alternatives: www.apple.com, dl.google.com, www.yahoo.com"
    ISSUES=$((ISSUES + 1))
  fi

  # 2. Check if port 443 is available
  info "Checking port 443 availability..."
  PORT_CHECK=$(run_on_server "ss -tlnp sport = :443 2>/dev/null | grep LISTEN" || true)
  if [[ -z "$PORT_CHECK" ]]; then
    ok "Port 443 is available"
  else
    # Extract process name (works on both GNU and BSD grep)
    PORT_USER=$(echo "$PORT_CHECK" | sed -n 's/.*users:(("\([^"]*\)".*/\1/p' | head -1)
    [[ -z "$PORT_USER" ]] && PORT_USER="unknown"
    if [[ "$PORT_USER" == "haproxy" || "$PORT_USER" == "3x-ui" || "$PORT_USER" == "xray" || "$PORT_USER" == "caddy" ]]; then
      ok "Port 443 is in use by $PORT_USER (Meridian — OK)"
    else
      warn "Port 443 is in use by: $PORT_USER"
      warn "  Meridian needs port 443. Stop the conflicting service first."
      ISSUES=$((ISSUES + 1))
    fi
  fi

  # 3. Check if port 443 is reachable from outside (TCP-level, no TLS)
  info "Checking port 443 external reachability..."
  if timeout 5 bash -c "echo >/dev/tcp/$SERVER_IP/443" 2>/dev/null; then
    ok "Port 443 is reachable from outside"
  else
    # Could be nothing listening yet (pre-install) — check from server side
    PORT_LISTEN=$(run_on_server "ss -tlnp sport = :443 2>/dev/null | grep -c LISTEN" || echo "0")
    if [[ "$PORT_LISTEN" == "0" ]]; then
      ok "Port 443 not yet listening (expected before install)"
    else
      warn "Port 443 is listening on server but not reachable from outside"
      warn "  Check your VPS provider's firewall/security group settings."
      ISSUES=$((ISSUES + 1))
    fi
  fi

  # 4. Check if domain resolves correctly (if provided)
  if [[ -n "$DOMAIN" ]]; then
    info "Checking domain DNS ($DOMAIN)..."
    DNS_RESULT=$(run_on_server "dig +short $DOMAIN @8.8.8.8 2>/dev/null" || true)
    if [[ "$DNS_RESULT" == *"$SERVER_IP"* ]]; then
      ok "$DOMAIN resolves to $SERVER_IP"
    elif [[ -n "$DNS_RESULT" ]]; then
      warn "$DOMAIN resolves to $DNS_RESULT (expected $SERVER_IP)"
      warn "  If using Cloudflare proxy (orange cloud), this is OK after initial setup."
      warn "  For first install, set DNS to 'DNS only' (grey cloud)."
      ISSUES=$((ISSUES + 1))
    else
      warn "$DOMAIN does not resolve (no DNS record found)"
      ISSUES=$((ISSUES + 1))
    fi
  fi

  # 5. Check server OS
  info "Checking server OS..."
  OS_INFO=$(run_on_server "cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'" || true)
  if [[ "$OS_INFO" == *"Ubuntu"* || "$OS_INFO" == *"Debian"* ]]; then
    ok "Server OS: $OS_INFO"
  elif [[ -n "$OS_INFO" ]]; then
    warn "Server OS: $OS_INFO (tested on Ubuntu/Debian only)"
    ISSUES=$((ISSUES + 1))
  fi

  # 6. Check available disk space
  info "Checking disk space..."
  DISK_AVAIL=$(run_on_server "df -BG / 2>/dev/null | tail -1 | awk '{print \$4}' | tr -d 'G'" || true)
  if [[ -n "$DISK_AVAIL" ]] && [[ "$DISK_AVAIL" -ge 2 ]]; then
    ok "Disk space: ${DISK_AVAIL}G available"
  elif [[ -n "$DISK_AVAIL" ]]; then
    warn "Only ${DISK_AVAIL}G disk space available (need at least 2G)"
    ISSUES=$((ISSUES + 1))
  fi

  printf "\n"
  line
  printf "\n"
  if [[ "$ISSUES" -eq 0 ]]; then
    printf "  ${G}${B}All checks passed.${R} Ready to install.\n\n"
  else
    printf "  ${Y}${B}$ISSUES issue(s) found.${R} Review the warnings above.\n"
    printf "  The install may still work — these are advisory checks.\n\n"
  fi
  printf "  ${D}Something unexpected? Report it:${R}\n"
  printf "  ${C}https://github.com/uburuntu/meridian/issues${R}\n"
  printf "  ${D}Use --rage to collect diagnostics for your report.${R}\n\n"
  exit 0
fi

# --- Diagnostics ---
if [[ "$DIAGNOSTICS" == true ]]; then
  printf "\n"
  printf "  ${B}Meridian Diagnostics${R}\n"
  printf "  ${D}Collecting system info for bug reports...${R}\n"
  printf "  ${Y}Note: secrets (passwords, UUIDs, keys) are redacted.${R}\n"
  printf "\n"

  DIAG=""
  add_section() { DIAG="${DIAG}\n### $1\n\`\`\`\n$2\n\`\`\`\n"; }

  # Local info
  LOCAL_OS=$(uname -a 2>&1)
  ANSIBLE_VER=$(command -v ansible &>/dev/null && ansible --version 2>&1 | head -1 || echo "not installed")
  add_section "Local Machine" "OS: $LOCAL_OS\nAnsible: $ANSIBLE_VER"

  # Server info
  SERVER_OS=$(run_on_server "cat /etc/os-release 2>/dev/null | grep PRETTY_NAME" || echo "unknown")
  SERVER_KERNEL=$(run_on_server "uname -r" || echo "unknown")
  SERVER_UPTIME=$(run_on_server "uptime" || echo "unknown")
  SERVER_DISK=$(run_on_server "df -h / 2>/dev/null | tail -1" || echo "unknown")
  SERVER_MEM=$(run_on_server "free -h 2>/dev/null | grep Mem" || echo "unknown")
  add_section "Server" "$SERVER_OS\nKernel: $SERVER_KERNEL\n$SERVER_UPTIME\nDisk: $SERVER_DISK\nMemory: $SERVER_MEM"

  # Docker
  DOCKER_VER=$(run_on_server "docker --version 2>&1" || echo "not installed")
  DOCKER_PS=$(run_on_server "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>&1" || echo "no containers")
  add_section "Docker" "$DOCKER_VER\n$DOCKER_PS"

  # 3x-ui logs (last 20 unique lines, secrets redacted)
  XRAY_LOGS=$(run_on_server "docker logs 3x-ui --tail 50 2>&1 | grep -v '^\s*$' | sort -u | tail -20" || echo "container not running")
  XRAY_LOGS=$(printf '%s' "$XRAY_LOGS" | sed -E 's/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[UUID-REDACTED]/g; s/([Pp]assword|[Kk]ey|[Ss]ecret)[=: ]*[^ ]*/\1=[REDACTED]/g')
  add_section "3x-ui Logs (last 30 lines)" "$XRAY_LOGS"

  # Ports
  PORTS=$(run_on_server "ss -tlnp sport = :443 or sport = :80 or sport = :8443 or sport = :8444 2>&1" || echo "unknown")
  add_section "Listening Ports" "$PORTS"

  # Firewall
  UFW=$(run_on_server "ufw status verbose 2>&1" || echo "ufw not available")
  add_section "Firewall (UFW)" "$UFW"

  # HAProxy
  HAPROXY_STATUS=$(run_on_server "systemctl is-active haproxy 2>&1" || echo "not installed")
  add_section "HAProxy" "Status: $HAPROXY_STATUS"

  # Caddy
  CADDY_STATUS=$(run_on_server "systemctl is-active caddy 2>&1" || echo "not installed")
  CADDY_LOGS=$(run_on_server "journalctl -u caddy --no-pager -n 10 2>&1" || echo "no logs")
  add_section "Caddy" "Status: $CADDY_STATUS\nRecent logs:\n$CADDY_LOGS"

  # SNI check
  SNI_HOST="${SNI:-www.microsoft.com}"
  SNI_CHECK=$(run_on_server "echo | openssl s_client -connect $SNI_HOST:443 -servername $SNI_HOST 2>/dev/null | grep -E 'subject=|issuer=|CONNECTED'" || echo "unreachable")
  add_section "SNI Target ($SNI_HOST)" "${SNI_CHECK:-unreachable}"

  # DNS (if domain known)
  SAVED_DOMAIN=""
  for cred_dir in "$HOME/meridian" "$ORIG_PWD/meridian"; do
    if [[ -f "$cred_dir/proxy.yml" ]]; then
      SAVED_DOMAIN=$(grep '^domain:' "$cred_dir/proxy.yml" 2>/dev/null | awk '{print $2}' | tr -d '"' || true)
      [[ -n "$SAVED_DOMAIN" ]] && break
    fi
  done
  if [[ -n "$DOMAIN" || -n "$SAVED_DOMAIN" ]]; then
    CHECK_DOMAIN="${DOMAIN:-$SAVED_DOMAIN}"
    DNS_RESULT=$(run_on_server "dig +short $CHECK_DOMAIN @8.8.8.8 2>/dev/null" || echo "dig not available")
    add_section "Domain DNS ($CHECK_DOMAIN)" "$DNS_RESULT"
  fi

  printf "\n"
  line
  printf "\n"
  printf "  ${B}Diagnostics collected.${R}\n\n"
  printf "  1. Review the output below for any private info you want to remove\n"
  printf "  2. Copy the markdown block into a new issue:\n"
  printf "     ${C}https://github.com/uburuntu/meridian/issues/new${R}\n"
  printf "\n"
  line
  printf "\n"

  # Output as markdown
  printf '%b' "$DIAG"

  printf "\n"
  line
  printf "\n"
  printf "  ${D}Secrets (UUIDs, passwords, keys) are auto-redacted.${R}\n\n"
  exit 0
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
# Fetch credentials from the server if not found locally (e.g., previous run was in local mode)
if [[ "$CRED_FOUND" != true && "$LOCAL_MODE" != true ]]; then
  REMOTE_CRED=$(ssh -o BatchMode=yes -o ConnectTimeout=3 "${ANSIBLE_USER}@${SERVER_IP}" \
    "cat /root/meridian/proxy.yml 2>/dev/null || cat \$HOME/meridian/proxy.yml 2>/dev/null" </dev/null 2>/dev/null || true)
  if [[ -n "$REMOTE_CRED" && "$REMOTE_CRED" == *"panel_configured"* ]]; then
    mkdir -p credentials
    printf '%s\n' "$REMOTE_CRED" > credentials/proxy.yml
    # Also save locally for future runs
    mkdir -p "$HOME/meridian"
    printf '%s\n' "$REMOTE_CRED" > "$HOME/meridian/proxy.yml"
    ok "Fetched credentials from server"
    CRED_FOUND=true
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
printf "  Send the HTML file to whoever needs it — they scan the QR code and connect.\n"
printf "\n  ${D}Feedback, issues, or ideas: https://github.com/uburuntu/meridian/issues${R}\n"
printf "  ${D}This project evolves based on your feedback — every report helps.${R}\n\n"
