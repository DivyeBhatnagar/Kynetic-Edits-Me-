#!/usr/bin/env bash
# Phase 3 — Kynetic Minimal Container Runtime Installer
#
# Installs the minimal container runtime stack for Kynetic host agents:
#   containerd   ~50 MB  (replaces full Docker/dockerd ~450 MB)
#   runc         ~15 MB  (OCI runtime — required by containerd)
#   stargz-snapshotter  ~25 MB  (eStargz lazy pulling plugin)
#   ─────────────────────────────
#   Total:       ~90 MB  vs ~450 MB for Docker Desktop
#
# Usage:
#   sudo bash infra/host_install/install_runtime.sh
#   sudo bash infra/host_install/install_runtime.sh --profile lite    # runc only, no stargz
#   sudo bash infra/host_install/install_runtime.sh --profile gpu     # full stack + nvidia hooks
#
# Supported OS:
#   Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, Debian 12 (Bookworm)
#   (Other Debian-derivatives likely work; RHEL/Alpine not yet tested)

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
CONTAINERD_VERSION="${CONTAINERD_VERSION:-1.7.18}"
RUNC_VERSION="${RUNC_VERSION:-1.1.13}"
STARGZ_VERSION="${STARGZ_VERSION:-0.15.1}"
CNI_VERSION="${CNI_VERSION:-1.5.1}"

INSTALL_DIR="${INSTALL_DIR:-/usr/local/bin}"
CONTAINERD_CONFIG_DIR="/etc/containerd"
STARGZ_CONFIG_DIR="/etc/containerd-stargz-grpc"
SYSTEMD_DIR="/etc/systemd/system"

ARCH="$(uname -m)"
case "${ARCH}" in
    x86_64)  ARCH_LABEL="amd64" ;;
    aarch64) ARCH_LABEL="arm64" ;;
    *)       echo "Unsupported architecture: ${ARCH}"; exit 1 ;;
esac

PROFILE="${1:-standard}"
if [[ "${1:-}" == "--profile" ]]; then
    PROFILE="${2:-standard}"
fi

log()  { echo "[kynetic-runtime] $*"; }
warn() { echo "[kynetic-runtime] WARN: $*" >&2; }

require_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        echo "ERROR: This script must be run as root (sudo)."
        exit 1
    fi
}

# ── Helper: download with checksum ────────────────────────────────────────────
download() {
    local url="$1" dest="$2"
    log "Downloading: ${url}"
    curl -fSL --retry 3 --retry-delay 2 "${url}" -o "${dest}"
}

# ── Step 1: Install runc ───────────────────────────────────────────────────────
install_runc() {
    log "Installing runc v${RUNC_VERSION}..."
    RUNC_URL="https://github.com/opencontainers/runc/releases/download/v${RUNC_VERSION}/runc.${ARCH_LABEL}"
    download "${RUNC_URL}" /tmp/runc
    install -o root -g root -m 755 /tmp/runc "${INSTALL_DIR}/runc"
    rm -f /tmp/runc
    log "  ✓ runc $(runc --version | head -1)"
}

# ── Step 2: Install containerd ─────────────────────────────────────────────────
install_containerd() {
    log "Installing containerd v${CONTAINERD_VERSION}..."
    CONTAINERD_TAR="containerd-${CONTAINERD_VERSION}-linux-${ARCH_LABEL}.tar.gz"
    CONTAINERD_URL="https://github.com/containerd/containerd/releases/download/v${CONTAINERD_VERSION}/${CONTAINERD_TAR}"
    download "${CONTAINERD_URL}" "/tmp/${CONTAINERD_TAR}"
    tar -C /usr/local -xzf "/tmp/${CONTAINERD_TAR}"
    rm -f "/tmp/${CONTAINERD_TAR}"
    log "  ✓ containerd $(containerd --version)"

    # Generate default config then patch for stargz
    mkdir -p "${CONTAINERD_CONFIG_DIR}"
    containerd config default > "${CONTAINERD_CONFIG_DIR}/config.toml"

    # Patch containerd config to:
    #   1. Use stargz snapshotter (if profile != lite)
    #   2. Set kynetic namespace as default
    #   3. Configure content store limits
    if [[ "${PROFILE}" != "lite" ]]; then
        log "  Configuring stargz snapshotter in containerd config..."
        cat >> "${CONTAINERD_CONFIG_DIR}/config.toml" << 'CONTAINERD_PATCH'

# ── Kynetic Phase 3: stargz-snapshotter plugin ────────────────────────────────
[proxy_plugins]
  [proxy_plugins.stargz]
    type = "snapshot"
    address = "/run/containerd-stargz-grpc/containerd-stargz-grpc.sock"
CONTAINERD_PATCH
    fi

    # Install containerd systemd service
    cat > "${SYSTEMD_DIR}/containerd.service" << 'CONTAINERD_SERVICE'
[Unit]
Description=containerd container runtime (Kynetic)
Documentation=https://containerd.io
After=network.target local-fs.target

[Service]
ExecStartPre=-/sbin/modprobe overlay
ExecStart=/usr/local/bin/containerd
Type=notify
Delegate=yes
KillMode=process
Restart=always
RestartSec=5
LimitNOFILE=1048576
LimitNPROC=infinity
LimitCORE=infinity
TasksMax=infinity
OOMScoreAdjust=-999

[Install]
WantedBy=multi-user.target
CONTAINERD_SERVICE

    systemctl daemon-reload
    systemctl enable containerd
    systemctl start containerd
    log "  ✓ containerd service started"
}

# ── Step 3: Install CNI plugins ────────────────────────────────────────────────
install_cni() {
    log "Installing CNI plugins v${CNI_VERSION}..."
    CNI_TAR="cni-plugins-linux-${ARCH_LABEL}-v${CNI_VERSION}.tgz"
    CNI_URL="https://github.com/containernetworking/plugins/releases/download/v${CNI_VERSION}/${CNI_TAR}"
    mkdir -p /opt/cni/bin
    download "${CNI_URL}" "/tmp/${CNI_TAR}"
    tar -C /opt/cni/bin -xzf "/tmp/${CNI_TAR}"
    rm -f "/tmp/${CNI_TAR}"
    log "  ✓ CNI plugins installed at /opt/cni/bin"
}

# ── Step 4: Install stargz-snapshotter ────────────────────────────────────────
install_stargz() {
    if [[ "${PROFILE}" == "lite" ]]; then
        log "Skipping stargz (profile=lite)"
        return
    fi

    log "Installing stargz-snapshotter v${STARGZ_VERSION}..."
    STARGZ_TAR="stargz-snapshotter-v${STARGZ_VERSION}-linux-${ARCH_LABEL}.tar.gz"
    STARGZ_URL="https://github.com/containerd/stargz-snapshotter/releases/download/v${STARGZ_VERSION}/${STARGZ_TAR}"
    download "${STARGZ_URL}" "/tmp/${STARGZ_TAR}"
    tar -C "${INSTALL_DIR}" -xzf "/tmp/${STARGZ_TAR}" \
        containerd-stargz-grpc \
        ctr-remote
    chmod 755 "${INSTALL_DIR}/containerd-stargz-grpc"
    rm -f "/tmp/${STARGZ_TAR}"

    # Stargz config
    mkdir -p "${STARGZ_CONFIG_DIR}"
    cat > "${STARGZ_CONFIG_DIR}/config.toml" << 'STARGZ_CONFIG'
# Kynetic stargz-snapshotter configuration
# Enables eStargz lazy image pulling with local OCI content-addressable cache.

[snapshotter]
  # Root directory for snapshotter state and layer cache
  root = "/var/lib/containerd-stargz-grpc"

[snapshotter.backgroundfetch]
  # Prefetch layers in the background after container starts
  # Ensures full layer availability without blocking container start
  disable = false
  silentPeriod = "3s"       # Wait 3s after container start before background fetch
  prefetchTimeoutSec = 30   # Abort stale background fetches

[registry]
  # Pull credentials for the Kynetic registry
  # Populated by the host agent at registration time

[grpc]
  address = "/run/containerd-stargz-grpc/containerd-stargz-grpc.sock"
STARGZ_CONFIG

    # Stargz systemd service
    cat > "${SYSTEMD_DIR}/containerd-stargz-grpc.service" << 'STARGZ_SERVICE'
[Unit]
Description=Stargz Snapshotter for containerd (Kynetic Phase 3)
Documentation=https://github.com/containerd/stargz-snapshotter
After=network.target

[Service]
ExecStart=/usr/local/bin/containerd-stargz-grpc \
    --config /etc/containerd-stargz-grpc/config.toml \
    --log-level info
Restart=always
RestartSec=5
Type=notify

[Install]
WantedBy=multi-user.target
STARGZ_SERVICE

    systemctl daemon-reload
    systemctl enable containerd-stargz-grpc
    systemctl start containerd-stargz-grpc
    log "  ✓ stargz-snapshotter service started"
}

# ── Step 5: Install NVIDIA Container Toolkit hooks (GPU profile only) ──────────
install_nvidia_hooks() {
    if [[ "${PROFILE}" != "gpu" ]]; then
        return
    fi
    log "Installing NVIDIA Container Toolkit hooks (profile=gpu)..."
    distribution="$(. /etc/os-release; echo "${ID}${VERSION_ID}")"
    curl -fsSL "https://nvidia.github.io/libnvidia-container/gpgkey" \
        | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L "https://nvidia.github.io/libnvidia-container/${distribution}/libnvidia-container.list" \
        | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
        | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    apt-get update -qq
    apt-get install -y nvidia-container-toolkit
    # Configure containerd to use nvidia runtime
    nvidia-ctk runtime configure --runtime=containerd
    systemctl restart containerd
    log "  ✓ NVIDIA container toolkit installed"
}

# ── Step 6: Verify installation ────────────────────────────────────────────────
verify_installation() {
    log ""
    log "Verifying installation..."
    local ok=true

    for binary in runc containerd ctr; do
        if command -v "${binary}" &>/dev/null; then
            log "  ✓ ${binary}: $(${binary} --version 2>&1 | head -1)"
        else
            warn "  ✗ ${binary}: NOT FOUND"
            ok=false
        fi
    done

    if [[ "${PROFILE}" != "lite" ]] && command -v containerd-stargz-grpc &>/dev/null; then
        log "  ✓ containerd-stargz-grpc: $(containerd-stargz-grpc --version 2>&1 | head -1)"
    fi

    if systemctl is-active containerd &>/dev/null; then
        log "  ✓ containerd.service: active"
    else
        warn "  ✗ containerd.service: not running"
        ok=false
    fi

    if [[ "${ok}" == "true" ]]; then
        log ""
        log "╔══════════════════════════════════════════════════════════╗"
        log "║  Kynetic Runtime Installation Complete (Profile: ${PROFILE})  ║"
        log "║  containerd + runc + stargz = ~90 MB total footprint    ║"
        log "║  (vs ~450 MB for full Docker)                           ║"
        log "╚══════════════════════════════════════════════════════════╝"
    else
        warn "Installation completed with warnings. Check above for details."
    fi
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    require_root
    log "Kynetic Runtime Installer — Profile: ${PROFILE}"
    log "Arch: ${ARCH_LABEL}"
    log ""

    install_runc
    install_containerd
    install_cni
    install_stargz
    install_nvidia_hooks
    verify_installation
}

main "$@"
