#!/usr/bin/env python3
"""Test Reality connections (direct + via relay) through the deployed exit node.

Uses the default CONNECT_TEST_URL (ifconfig.me) since xray blocks private IPs
(geoip:private routing rule). IP match is disabled because the Docker bridge
IP won't match the public egress IP.

XHTTP/WSS skipped until domain mode + Pebble ACME is wired (phase 2).
Exit code 0 = all passed, 1 = at least one failure.
"""

from __future__ import annotations

import os
import sys

from meridian.cluster import ClusterConfig
from meridian.xray_client import (
    build_test_configs_from_cluster,
    ensure_xray_binary,
    test_connection,
)

EXIT_IP = os.environ.get("EXIT_IP", "172.30.0.10")
CLIENT_UUID = os.environ.get("CLIENT_UUID", "")

if not CLIENT_UUID:
    print("FAIL: CLIENT_UUID env var not set — need a real user UUID for auth")
    sys.exit(1)

cluster = ClusterConfig.load()
if not cluster.is_configured:
    print("FAIL: cluster not configured — deploy first")
    sys.exit(1)

configs = build_test_configs_from_cluster(cluster, EXIT_IP, uuid=CLIENT_UUID)

# Reality only; IP match disabled (Docker NAT → public IP ≠ bridge IP)
selected = [(label, cfg, False) for label, cfg, _ in configs if "Reality" in label]

if not selected:
    print("FAIL: no Reality configs generated — check cluster config and node keys")
    sys.exit(1)

xray_bin = ensure_xray_binary()
if not xray_bin:
    print("FAIL: could not obtain xray binary")
    sys.exit(1)

print(f"  Testing {len(selected)} Reality config(s)...")
passed = 0
failed = 0

for label, config, expect_ip_match in selected:
    socks_port = config["inbounds"][0]["port"]
    ok, detail = test_connection(xray_bin, config, EXIT_IP, socks_port, label, expect_ip_match)
    status = "PASS" if ok else "FAIL"
    print(f"    {status}  {label}: {detail}")
    if ok:
        passed += 1
    else:
        failed += 1

print(f"  {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
