#!/bin/bash
# Mock systemctl for E2E testing in containers without systemd.
# Returns 0 for all commands to prevent provisioner step failures.
# Only used in the E2E test container, never in production.
exit 0
