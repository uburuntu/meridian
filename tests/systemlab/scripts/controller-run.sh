#!/usr/bin/env bash
# System lab controller — deploys Remnawave exit + relay, tests connections,
# verifies key preservation on redeploy, then tears down.
set -euo pipefail

EXIT_IP=${EXIT_IP:?}
RELAY_IP=${RELAY_IP:?}
export MERIDIAN_HOME=${MERIDIAN_HOME:-/tmp/meridian-home}
export PYTHONUNBUFFERED=1
mkdir -p "$MERIDIAN_HOME" /root/.ssh

PASS=0
FAIL=0
pass()      { PASS=$((PASS+1)); echo "    ✓ $1"; }
fail_test() { FAIL=$((FAIL+1)); echo "    ✗ FAIL: $1"; }

# ── Stage 1: SSH setup ───────────────────────────────────
echo ""
echo "═══════════════════════════════════════"
echo "  Stage 1: SSH & systemd setup"
echo "═══════════════════════════════════════"

echo ">>> Scanning SSH host keys..."
for host in "$EXIT_IP" "$RELAY_IP"; do
  ok=0
  for i in $(seq 1 60); do
    if ssh-keyscan -T 2 "$host" >> /root/.ssh/known_hosts 2>/dev/null; then
      echo "    $host: key acquired"
      ok=1
      break
    fi
    sleep 2
  done
  [ "$ok" -eq 1 ] || { echo "FATAL: SSH not ready on $host after 2 min"; exit 1; }
done

cp /workspace/tests/systemlab/fixtures/id_ed25519 /root/.ssh/id_ed25519
chmod 600 /root/.ssh/id_ed25519

cat >/root/.ssh/config <<'EOF'
Host *
  User root
  IdentityFile /root/.ssh/id_ed25519
  BatchMode yes
  StrictHostKeyChecking yes
  ConnectTimeout 10
  LogLevel ERROR
EOF
chmod 600 /root/.ssh/config

# Wait for systemd boot on both nodes
for label_ip in "exit-node:$EXIT_IP" "relay-node:$RELAY_IP"; do
  label=${label_ip%%:*}; ip=${label_ip#*:}
  echo ">>> Waiting for systemd on $label..."
  for i in $(seq 1 30); do
    state=$(ssh root@"$ip" systemctl is-system-running 2>/dev/null || true)
    if [ "$state" = "running" ] || [ "$state" = "degraded" ]; then
      echo "    $label: $state"
      break
    fi
    [ "$i" -eq 30 ] && { echo "FATAL: $label systemd not ready"; exit 1; }
    sleep 2
  done
done

# Install Pebble CA on exit node (enables future domain-mode cert tests)
if [ -f /workspace/tests/systemlab/fixtures/pebble-ca.pem ]; then
  echo ">>> Installing Pebble root CA on exit node..."
  scp /workspace/tests/systemlab/fixtures/pebble-ca.pem root@"$EXIT_IP":/usr/local/share/ca-certificates/pebble.crt
  ssh root@"$EXIT_IP" update-ca-certificates 2>/dev/null
  echo "    Pebble CA trusted"
fi

# ── Stage 2: Fresh deploy ────────────────────────────────
echo ""
echo "═══════════════════════════════════════"
echo "  Stage 2: Fresh deploy"
echo "═══════════════════════════════════════"

echo ">>> Deploying exit node ($EXIT_IP)..."
meridian deploy "$EXIT_IP" --user root --yes --no-harden --sni www.google.com

# ── Stage 3: Verify deployment ───────────────────────────
echo ""
echo "═══════════════════════════════════════"
echo "  Stage 3: Verify deployment"
echo "═══════════════════════════════════════"

# Check Remnawave containers
for container in remnawave remnawave-db remnawave-redis remnawave-node; do
  if ssh root@"$EXIT_IP" docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${container}$"; then
    pass "$container container running"
  else
    fail_test "$container container not running"
  fi
done

# Check nginx
if ssh root@"$EXIT_IP" nginx -t 2>&1 | grep -q "syntax is ok"; then
  pass "nginx config valid"
else
  fail_test "nginx config invalid"
fi

if ssh root@"$EXIT_IP" ss -tlnp sport = :443 2>/dev/null | grep -q LISTEN; then
  pass "port 443 listening"
else
  fail_test "port 443 not listening"
fi

# Check cluster config created
if [ -f "$MERIDIAN_HOME/cluster.yml" ]; then
  pass "cluster.yml created"
else
  fail_test "cluster.yml not created after deploy"
fi

# Check fleet status (node connected)
echo ">>> Checking fleet status..."
if meridian fleet status 2>&1 | grep -q "connected"; then
  pass "node shows connected in fleet status"
else
  fail_test "node not connected in fleet status"
fi

# ── Stage 4: Client lifecycle ────────────────────────────
echo ""
echo "═══════════════════════════════════════"
echo "  Stage 4: Client lifecycle"
echo "═══════════════════════════════════════"

echo ">>> Adding client alice..."
if meridian client add alice 2>&1; then
  pass "client add alice"
else
  fail_test "client add alice"
fi

echo ">>> Listing clients..."
if meridian client list 2>&1 | grep -q "alice"; then
  pass "client list shows alice"
else
  fail_test "client list does not show alice"
fi

echo ">>> Showing client alice..."
if meridian client show alice 2>&1; then
  pass "client show alice"
else
  fail_test "client show alice"
fi

echo ">>> Removing client alice..."
if meridian client remove alice --yes 2>&1; then
  pass "client remove alice"
else
  fail_test "client remove alice"
fi

# Verify alice is gone
if meridian client list 2>&1 | grep -q "alice"; then
  fail_test "alice still appears after remove"
else
  pass "alice removed from client list"
fi

# ── Stage 5: Relay deploy ────────────────────────────────
echo ""
echo "═══════════════════════════════════════"
echo "  Stage 5: Relay deploy"
echo "═══════════════════════════════════════"

echo ">>> Deploying relay ($RELAY_IP -> $EXIT_IP)..."
meridian relay deploy "$RELAY_IP" --exit "$EXIT_IP" --sni www.google.com --yes

if ssh root@"$RELAY_IP" systemctl is-active meridian-relay 2>/dev/null | grep -q active; then
  pass "meridian-relay service active"
else
  fail_test "meridian-relay service not active"
fi

echo ">>> Checking relay list..."
if meridian relay list 2>&1 | grep -q "$RELAY_IP"; then
  pass "relay appears in relay list"
else
  fail_test "relay not in relay list"
fi

# ── Stage 6: Connection test ─────────────────────────────
echo ""
echo "═══════════════════════════════════════"
echo "  Stage 6: Connection test"
echo "═══════════════════════════════════════"

echo ">>> Getting default client UUID..."
# The default client was created during deploy
CLIENT_UUID=$(meridian --json client show default 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['uuid'])" 2>/dev/null || true)

if [ -z "$CLIENT_UUID" ]; then
  fail_test "could not get default client UUID"
else
  pass "default client UUID: ${CLIENT_UUID:0:8}..."

  echo ">>> Running Reality connection tests..."
  export CLIENT_UUID
  if python3 /workspace/tests/systemlab/scripts/test-connections.py; then
    pass "Reality connection tests passed"
  else
    fail_test "Reality connection tests failed"
  fi
fi

# ── Stage 7: Redeploy (key preservation) ─────────────────
echo ""
echo "═══════════════════════════════════════"
echo "  Stage 7: Redeploy (key preservation)"
echo "═══════════════════════════════════════"

echo ">>> Capturing Reality keys before redeploy..."
BEFORE_PUB_KEY=$(meridian --json node list 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
nodes = data if isinstance(data, list) else data.get('nodes', [])
for n in nodes:
    pk = n.get('reality_public_key', '') or n.get('public_key', '')
    if pk:
        print(pk)
        break
" 2>/dev/null || true)

if [ -z "$BEFORE_PUB_KEY" ]; then
  echo "    WARN: could not extract public key from node list (--json output may differ)"
  echo "    Falling back to cluster.yml..."
  BEFORE_PUB_KEY=$(python3 -c "
from meridian.cluster import ClusterConfig
c = ClusterConfig.load()
if c.nodes:
    print(c.nodes[0].reality_public_key)
" 2>/dev/null || true)
fi

if [ -n "$BEFORE_PUB_KEY" ]; then
  pass "captured before-key: ${BEFORE_PUB_KEY:0:12}..."
else
  fail_test "could not capture Reality public key before redeploy"
fi

echo ">>> Redeploying exit node..."
meridian deploy "$EXIT_IP" --user root --yes --sni www.google.com

echo ">>> Verifying keys preserved..."
AFTER_PUB_KEY=$(python3 -c "
from meridian.cluster import ClusterConfig
c = ClusterConfig.load()
if c.nodes:
    print(c.nodes[0].reality_public_key)
" 2>/dev/null || true)

if [ -n "$BEFORE_PUB_KEY" ] && [ "$BEFORE_PUB_KEY" = "$AFTER_PUB_KEY" ]; then
  pass "Reality keys preserved after redeploy"
else
  fail_test "Reality keys changed! Before=$BEFORE_PUB_KEY After=$AFTER_PUB_KEY"
fi

# Verify clients still work after redeploy
if [ -n "$CLIENT_UUID" ]; then
  echo ">>> Re-testing connections after redeploy..."
  if python3 /workspace/tests/systemlab/scripts/test-connections.py; then
    pass "connections still work after redeploy"
  else
    fail_test "connections broken after redeploy"
  fi
fi

# ── Stage 8: Teardown ────────────────────────────────────
echo ""
echo "═══════════════════════════════════════"
echo "  Stage 8: Teardown"
echo "═══════════════════════════════════════"

echo ">>> Removing relay..."
meridian relay remove "$RELAY_IP" --yes 2>&1 || echo "    WARN: relay remove failed (non-fatal)"

echo ">>> Tearing down exit node..."
meridian teardown "$EXIT_IP" --yes 2>&1 || echo "    WARN: teardown failed (non-fatal)"

# Verify port 443 freed
if ssh root@"$EXIT_IP" ss -tlnp sport = :443 2>/dev/null | grep -q LISTEN; then
  fail_test "port 443 still listening after teardown"
else
  pass "port 443 freed"
fi

# Verify Remnawave containers stopped
for container in remnawave remnawave-node; do
  if ssh root@"$EXIT_IP" docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${container}$"; then
    fail_test "$container still running after teardown"
  else
    pass "$container stopped"
  fi
done

# ── Summary ──────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════"
echo "  PASS: $PASS   FAIL: $FAIL"
echo "═══════════════════════════════════════"
[ "$FAIL" -eq 0 ] || exit 1
