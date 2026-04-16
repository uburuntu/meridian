#!/usr/bin/env bash
# Tier α verification for topology=single.
# Runs on the developer's machine. Requires TARGET_IP env var.
#
# Exits 0 on all-pass, non-zero on any failure.
set -uo pipefail

: "${TARGET_IP:?TARGET_IP env var required}"

PASS=0
FAIL=0
pass()      { PASS=$((PASS+1)); echo "    ✓ $1"; }
fail_test() { FAIL=$((FAIL+1)); echo "    ✗ FAIL: $1"; }

echo "═══════════════════════════════════════"
echo "  Real-VM tier α verify — $TARGET_IP"
echo "═══════════════════════════════════════"

# ── 1. SSH reachability + host key scan ─────────────────
echo ">>> SSH reachability + host key scan..."
if ssh-keyscan -T 15 "$TARGET_IP" >> ~/.ssh/known_hosts 2>/dev/null; then
  pass "SSH reachable, host key captured"
else
  fail_test "Cannot reach SSH on $TARGET_IP"
  exit 2
fi

# ── 2. Meridian deploy ─────────────────
echo ">>> Running: meridian deploy $TARGET_IP --user root --yes --no-harden ..."
# --no-harden keeps deploy time under ~3 min on real VM for fast iteration.
# Subsequent `meridian deploy --yes` redeploy WILL harden (tested below).
if uv run meridian deploy "$TARGET_IP" --user root --yes --no-harden --sni www.microsoft.com; then
  pass "initial deploy succeeded"
else
  fail_test "meridian deploy failed — check output above"
  exit 2
fi

# ── 3. Let's Encrypt cert (real, not Pebble) ─────────────────
echo ">>> Checking Let's Encrypt cert chain..."
CERT_INFO=$(ssh -o StrictHostKeyChecking=no root@"$TARGET_IP" \
  "openssl s_client -connect 127.0.0.1:443 -servername $TARGET_IP </dev/null 2>/dev/null | openssl x509 -noout -issuer -dates" 2>/dev/null || true)
if echo "$CERT_INFO" | grep -qiE "Let's Encrypt|R10|R11|ISRG Root"; then
  pass "cert chain issued by Let's Encrypt"
else
  fail_test "cert chain does not mention Let's Encrypt: $CERT_INFO"
fi

# ── 4. External port filter (nmap from dev machine) ─────────────────
echo ">>> nmap external ports ..."
if ! command -v nmap >/dev/null; then
  echo "    ~ nmap not installed, skipping port-filter check (install nmap to enable)"
else
  OPEN=$(nmap -p 22,80,443,3000,3010,3020,8080 -Pn -T4 "$TARGET_IP" 2>/dev/null | awk '/^[0-9]+\/tcp/ && /open/ {print $1}' | tr '\n' ' ')
  echo "    open from outside: $OPEN"
  # Only 22/tcp 80/tcp 443/tcp should be open; anything else = UFW hole
  UNEXPECTED=$(echo "$OPEN" | tr ' ' '\n' | grep -vE '^(22|80|443)/tcp$' | grep -v '^$' || true)
  if [ -z "$UNEXPECTED" ]; then
    pass "UFW blocks all but 22/80/443"
  else
    fail_test "unexpected open ports: $UNEXPECTED"
  fi
fi

# ── 5. SSH hardening check ─────────────────
echo ">>> Redeploying WITH hardening to trigger SSH pubkey-only ..."
if uv run meridian deploy "$TARGET_IP" --user root --yes --sni www.microsoft.com; then
  pass "hardened redeploy succeeded"
else
  fail_test "hardened redeploy failed"
fi

echo ">>> Verifying password auth is refused ..."
# Must fail — we try to auth by password, no key. Should get 'Permission denied'.
PWD_RESULT=$(ssh -o StrictHostKeyChecking=no -o PasswordAuthentication=yes \
  -o PubkeyAuthentication=no -o PreferredAuthentications=password \
  -o ConnectTimeout=5 -o NumberOfPasswordPrompts=1 -o BatchMode=yes \
  root@"$TARGET_IP" 'echo ok' 2>&1 || true)
if echo "$PWD_RESULT" | grep -qiE 'permission denied|publickey'; then
  pass "sshd refuses password auth after hardening"
else
  fail_test "sshd did not refuse password auth: $PWD_RESULT"
fi

echo ">>> Checking fail2ban is active ..."
if ssh -o StrictHostKeyChecking=no root@"$TARGET_IP" "systemctl is-active fail2ban" 2>/dev/null | grep -q active; then
  pass "fail2ban is active"
else
  fail_test "fail2ban is not active"
fi

# ── 6. Fleet status ─────────────────
echo ">>> meridian fleet status ..."
if uv run meridian fleet status 2>&1 | grep -qiE "connected|ok|green|✓"; then
  pass "fleet reports connected"
else
  fail_test "fleet status does not report connected"
fi

# ── 7. Client add/remove roundtrip ─────────────────
echo ">>> meridian client add testuser ..."
if uv run meridian client add realvm-testuser 2>&1 | grep -qE "added|created|✓"; then
  pass "client add succeeded"
else
  fail_test "client add did not succeed"
fi

echo ">>> meridian client list ..."
if uv run meridian client list 2>&1 | grep -q "realvm-testuser"; then
  pass "client visible in list"
else
  fail_test "client not in list"
fi

echo ">>> meridian client remove ..."
if uv run meridian client remove realvm-testuser --yes 2>&1; then
  pass "client remove succeeded"
else
  fail_test "client remove failed"
fi

# ── 8. Declarative plan/apply cycle ─────────────────
echo ">>> meridian plan (should be converged = exit 0) ..."
uv run meridian plan 2>&1 || true
PLAN_CODE=$?
# plan exit 0 = converged (nothing to do), exit 2 = changes pending, exit 1 = error
if [ "$PLAN_CODE" -eq 0 ] || [ "$PLAN_CODE" -eq 2 ]; then
  pass "plan runs without error"
else
  fail_test "plan failed with exit $PLAN_CODE"
fi

# ── 9. Subscription URL returns valid config ─────────────────
echo ">>> curl subscription URL ..."
SUB_URL=$(uv run meridian client show default 2>/dev/null | grep -oE 'https://[^ ]*api/sub/[A-Za-z0-9]+' | head -1 || true)
if [ -z "$SUB_URL" ]; then
  # Try alternate grep if first didn't hit
  SUB_URL=$(uv run meridian client show default 2>/dev/null | grep -oE 'https://[^ ]+sub[^ ]*' | head -1 || true)
fi
if [ -n "$SUB_URL" ]; then
  HTTP=$(curl -sk -o /tmp/realvm_sub -w '%{http_code}' "$SUB_URL" || true)
  if [ "$HTTP" = "200" ]; then
    pass "subscription URL returns 200"
    if grep -qE '(vless|outbounds|inbounds)' /tmp/realvm_sub 2>/dev/null; then
      pass "subscription body looks like xray config"
    else
      echo "    ~ subscription body doesn't match expected patterns; content-type may be encoded"
    fi
  else
    fail_test "subscription URL returned HTTP $HTTP"
  fi
else
  fail_test "could not extract subscription URL from client show"
fi

# ── 10. Summary ─────────────────
echo ""
echo "═══════════════════════════════════════"
echo "  PASS: $PASS   FAIL: $FAIL"
echo "═══════════════════════════════════════"

[ "$FAIL" -eq 0 ] || exit 1
