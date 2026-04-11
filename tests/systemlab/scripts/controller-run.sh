#!/usr/bin/env bash
# System lab controller — deploys exit + relay, runs connection tests, tears down.
set -euo pipefail

EXIT_IP=${EXIT_IP:?}
RELAY_IP=${RELAY_IP:?}
export MERIDIAN_HOME=${MERIDIAN_HOME:-/tmp/meridian-home}
export PYTHONUNBUFFERED=1
mkdir -p "$MERIDIAN_HOME" /root/.ssh

PASS=0
FAIL=0
pass()      { PASS=$((PASS+1)); }
fail_test() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }

# ── SSH setup ──────────────────────────────────────────────
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

# ── Wait for systemd boot ─────────────────────────────────
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

# ── Install Pebble CA on exit node (enables future domain-mode cert tests) ──
if [ -f /workspace/tests/systemlab/fixtures/pebble-ca.pem ]; then
  echo ""
  echo ">>> Installing Pebble root CA on exit node..."
  scp /workspace/tests/systemlab/fixtures/pebble-ca.pem root@"$EXIT_IP":/usr/local/share/ca-certificates/pebble.crt
  ssh root@"$EXIT_IP" update-ca-certificates 2>/dev/null
  echo "    Pebble CA trusted"
fi

# ── Deploy exit node ───────────────────────────────────────
echo ""
echo ">>> Deploying exit node ($EXIT_IP)..."
meridian deploy "$EXIT_IP" --user root --yes --no-harden

if [ -f "$MERIDIAN_HOME/credentials/$EXIT_IP/proxy.yml" ]; then
  echo "    credentials created"; pass
else
  fail_test "proxy.yml not created after deploy"
fi

if ssh root@"$EXIT_IP" docker ps --format '{{.Names}}' 2>/dev/null | grep -q 3x-ui; then
  echo "    3x-ui container running"; pass
else
  fail_test "3x-ui container not running"
fi

if ssh root@"$EXIT_IP" nginx -t 2>&1 | grep -q "syntax is ok"; then
  echo "    nginx config valid"; pass
else
  fail_test "nginx config invalid"
fi

if ssh root@"$EXIT_IP" ss -tlnp sport = :443 2>/dev/null | grep -q nginx; then
  echo "    nginx listening on :443"; pass
else
  fail_test "nginx not listening on port 443"
fi

# ── Add client ─────────────────────────────────────────────
echo ""
echo ">>> Adding client alice..."
meridian client add alice
pass

# ── Deploy relay ───────────────────────────────────────────
echo ""
echo ">>> Deploying relay ($RELAY_IP -> $EXIT_IP)..."
meridian relay deploy "$RELAY_IP" --exit "$EXIT_IP" --sni www.google.com --yes

if ssh root@"$RELAY_IP" systemctl is-active meridian-relay 2>/dev/null | grep -q active; then
  echo "    meridian-relay service active"; pass
else
  fail_test "meridian-relay service not active"
fi

# ── Connection tests ───────────────────────────────────────
echo ""
echo ">>> Running Reality connection tests..."
if python3 /workspace/tests/systemlab/scripts/test-connections.py; then
  pass
else
  fail_test "Reality connection tests failed"
fi

# ── Teardown (non-fatal — relay credential sync has a known issue) ──
echo ""
echo ">>> Tearing down..."
meridian relay remove "$RELAY_IP" --exit "$EXIT_IP" --yes 2>&1 || echo "    WARN: relay remove failed (known credential sync issue)"
meridian teardown "$EXIT_IP" --yes 2>&1 || echo "    WARN: teardown failed (non-fatal)"

# ── Summary ────────────────────────────────────────────────
echo ""
echo "========================================="
echo "  PASS: $PASS   FAIL: $FAIL"
echo "========================================="
[ "$FAIL" -eq 0 ] || exit 1
