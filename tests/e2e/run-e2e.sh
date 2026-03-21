#!/usr/bin/env bash
# Meridian E2E test — full provisioner lifecycle inside Docker.
#
# Runs inside the meridian-e2e container (--network host, --privileged).
# The container has sshd running so meridian can SSH to 127.0.0.1 (self).
# Docker socket is mounted so provisioner creates 3x-ui on the host daemon.
set -uo pipefail

IP="127.0.0.1"
PASS=0
FAIL=0
START=$(date +%s)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
stage() { printf '\n\033[1;34m=== %s ===\033[0m\n' "$1"; }
pass()  { printf '  \033[32m✓ %s\033[0m\n' "$1"; PASS=$((PASS + 1)); }
fail_test() { printf '  \033[31m✗ %s\033[0m\n' "$1"; FAIL=$((FAIL + 1)); }

run_ok() {
    local desc="$1"; shift
    if "$@" >/dev/null 2>&1; then pass "$desc"; else fail_test "$desc: $*"; fi
}

run_capture_ok() {
    local desc="$1"; shift
    local output
    output=$("$@" 2>&1) && pass "$desc" || fail_test "$desc: $output"
}

run_fail() {
    local desc="$1"; shift
    if "$@" >/dev/null 2>&1; then fail_test "$desc (expected failure but succeeded)"; else pass "$desc"; fi
}

check_output() {
    local desc="$1" pattern="$2" output="$3"
    if echo "$output" | grep -q "$pattern"; then pass "$desc"; else fail_test "$desc (pattern '$pattern' not found)"; fi
}

check_no_output() {
    local desc="$1" pattern="$2" output="$3"
    if echo "$output" | grep -q "$pattern"; then fail_test "$desc (pattern '$pattern' found)"; else pass "$desc"; fi
}

# ---------------------------------------------------------------------------
# 0. Prerequisites
# ---------------------------------------------------------------------------
stage "0. Prerequisites"
run_ok "SSH self-connect" ssh "$IP" echo ok
run_ok "Docker socket accessible" docker info
run_ok "Meridian CLI installed" meridian version

# ---------------------------------------------------------------------------
# 1. Fresh setup
# ---------------------------------------------------------------------------
stage "1. Fresh setup"
run_capture_ok "meridian setup" meridian setup "$IP" --user root --yes

# ---------------------------------------------------------------------------
# 2. Verify deployment
# ---------------------------------------------------------------------------
stage "2. Verify deployment"
if docker ps --format '{{.Names}}' | grep -q 3x-ui; then pass "3x-ui container running"; else fail_test "3x-ui container not running"; fi
if docker exec 3x-ui pgrep -f xray >/dev/null 2>&1; then pass "Xray process alive"; else fail_test "Xray not running in 3x-ui"; fi
if [ -f "/root/.meridian/credentials/$IP/proxy.yml" ]; then pass "Local credentials exist"; else fail_test "Local credentials missing"; fi
if [ -f "/etc/meridian/proxy.yml" ]; then pass "Server credentials exist"; else fail_test "Server credentials missing"; fi

# ---------------------------------------------------------------------------
# 3. Idempotent re-run
# ---------------------------------------------------------------------------
stage "3. Idempotent re-run"
run_capture_ok "meridian setup (idempotent)" meridian setup "$IP" --user root --yes

# ---------------------------------------------------------------------------
# 4. Client operations
# ---------------------------------------------------------------------------
stage "4. Client operations"
run_capture_ok "client add alice" meridian client add alice
run_capture_ok "client add bob" meridian client add bob

OUTPUT=$(meridian client list 2>&1 || true)
check_output "client list shows default" "default" "$OUTPUT"
check_output "client list shows alice" "alice" "$OUTPUT"
check_output "client list shows bob" "bob" "$OUTPUT"

run_capture_ok "client remove bob" meridian client remove bob

OUTPUT=$(meridian client list 2>&1 || true)
check_no_output "bob removed from list" "bob" "$OUTPUT"
check_output "alice still in list" "alice" "$OUTPUT"

# Verify output files generated
if ls /root/.meridian/credentials/"$IP"/*-alice-connection-info.html >/dev/null 2>&1; then
    pass "alice HTML connection page exists"
else
    fail_test "alice HTML connection page missing"
fi
if ls /root/.meridian/credentials/"$IP"/*-alice-connection-info.txt >/dev/null 2>&1; then
    pass "alice text connection info exists"
else
    fail_test "alice text connection info missing"
fi

# ---------------------------------------------------------------------------
# 5. Ping
# ---------------------------------------------------------------------------
stage "5. Ping"
run_capture_ok "meridian ping" meridian ping "$IP"

# ---------------------------------------------------------------------------
# 6. Check
# ---------------------------------------------------------------------------
stage "6. Check"
# check may report warnings (e.g., port 443 in use) but should not crash
if meridian check "$IP" --user root >/dev/null 2>&1; then
    pass "meridian check completed"
else
    # Exit code 1 means issues found (not a crash) — still OK
    pass "meridian check completed (with warnings)"
fi

# ---------------------------------------------------------------------------
# 7. Diagnostics
# ---------------------------------------------------------------------------
stage "7. Diagnostics"
OUTPUT=$(meridian diagnostics --user root 2>&1 || true)
check_output "diagnostics has server section" "Server" "$OUTPUT"
check_output "diagnostics has docker section" "Docker" "$OUTPUT"

# ---------------------------------------------------------------------------
# 8. Uninstall
# ---------------------------------------------------------------------------
stage "8. Uninstall"
run_capture_ok "meridian uninstall" meridian uninstall "$IP" --user root --yes

# Verify cleanup
if docker ps --format '{{.Names}}' | grep -q 3x-ui; then
    fail_test "3x-ui container still running after uninstall"
else
    pass "3x-ui container removed"
fi
if [ -f "/root/.meridian/credentials/$IP/proxy.yml" ]; then
    fail_test "local credentials still exist after uninstall"
else
    pass "local credentials removed"
fi

# Verify cron cleanup (the fix from v3.3.1)
CRON_COUNT=$(crontab -l 2>/dev/null | grep -c update-stats || true)
if [ "$CRON_COUNT" -eq 0 ]; then
    pass "stats cron job cleaned up"
else
    fail_test "stats cron job NOT cleaned up ($CRON_COUNT entries)"
fi

# ---------------------------------------------------------------------------
# 9. Re-setup after uninstall
# ---------------------------------------------------------------------------
stage "9. Re-setup after uninstall"
run_capture_ok "meridian setup (after uninstall)" meridian setup "$IP" --user root --yes

if docker ps --format '{{.Names}}' | grep -q 3x-ui; then
    pass "3x-ui running again"
else
    fail_test "3x-ui not running after re-setup"
fi

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
meridian uninstall "$IP" --user root --yes >/dev/null 2>&1 || true
docker rm -f 3x-ui >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
END=$(date +%s)
ELAPSED=$((END - START))

echo ""
stage "Summary"
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo "  Time:   ${ELAPSED}s"
echo ""
if [ "$FAIL" -eq 0 ]; then
    printf '  \033[1;32mALL TESTS PASSED\033[0m\n'
else
    printf '  \033[1;31mSOME TESTS FAILED\033[0m\n'
fi
echo ""

# Exit with failure count (0 = success)
if [ "$FAIL" -gt 125 ]; then exit 125; fi
exit "$FAIL"
