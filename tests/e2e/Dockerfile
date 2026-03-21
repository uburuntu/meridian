FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------------------------
# System packages (includes everything from REQUIRED_PACKAGES in common.py
# so the InstallPackages step skips immediately)
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server openssh-client \
    python3 python3-pip python3-venv \
    curl wget openssl iproute2 qrencode dnsutils \
    ca-certificates gnupg sudo iptables ufw jq \
    socat unzip apt-transport-https \
    unattended-upgrades apt-listchanges \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Docker CE (full package so InstallDocker step skips)
# ---------------------------------------------------------------------------
RUN install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      -o /etc/apt/keyrings/docker.asc && \
    chmod 644 /etc/apt/keyrings/docker.asc && \
    . /etc/os-release && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
      https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
      > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      docker-ce docker-ce-cli containerd.io docker-compose-plugin && \
    rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# SSH: self-connect via key auth (root@127.0.0.1)
# ---------------------------------------------------------------------------
RUN mkdir -p /run/sshd /root/.ssh && \
    ssh-keygen -A && \
    ssh-keygen -t ed25519 -f /root/.ssh/id_ed25519 -N "" && \
    cat /root/.ssh/id_ed25519.pub >> /root/.ssh/authorized_keys && \
    chmod 700 /root/.ssh && \
    chmod 600 /root/.ssh/authorized_keys /root/.ssh/id_ed25519 && \
    printf 'Host 127.0.0.1\n  StrictHostKeyChecking no\n  UserKnownHostsFile /dev/null\n  LogLevel ERROR\n' \
      > /root/.ssh/config && \
    chmod 600 /root/.ssh/config

# ---------------------------------------------------------------------------
# Mock systemctl (no systemd in Docker)
# ---------------------------------------------------------------------------
COPY tests/e2e/mock-systemctl.sh /usr/local/bin/systemctl
RUN chmod +x /usr/local/bin/systemctl

# ---------------------------------------------------------------------------
# Install meridian from source
# ---------------------------------------------------------------------------
COPY . /src
WORKDIR /src
RUN pip install --break-system-packages --no-cache-dir .

# ---------------------------------------------------------------------------
# Entry point: start sshd, then run the E2E test script
# ---------------------------------------------------------------------------
COPY tests/e2e/run-e2e.sh /run-e2e.sh
RUN chmod +x /run-e2e.sh

WORKDIR /root
CMD ["/bin/bash", "-c", "/usr/sbin/sshd && sleep 1 && /run-e2e.sh"]
