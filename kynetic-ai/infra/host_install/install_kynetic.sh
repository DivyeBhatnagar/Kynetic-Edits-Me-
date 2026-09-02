#!/usr/bin/env bash
# Phase 6 — Kynetic Host Agent Installer with Tiered Profiles
#
# Installs the Kynetic AI host agent and its runtime dependencies
# in the smallest possible footprint matching the chosen profile.
#
# Profiles:
#   lite     < 180 MB — CPU-only edge nodes, lightweight tasks
#   standard < 250 MB — Standard microVM + container hosts
#   gpu      < 350 MB — AI/GPU rigs + datacenter clusters (+ ephemeral cache)
#
# Usage:
#   curl -fsSL https://install.kynetic.ai/agent | sudo bash
#   sudo bash infra/host_install/install_kynetic.sh --profile standard
#   sudo bash infra/host_install/install_kynetic.sh --profile gpu --backend https://api.kynetic.ai
#   sudo bash infra/host_install/install_kynetic.sh --dry-run
#
# Supported OS:
#   Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, Debian 12 (Bookworm)

set -euo pipefail

# ── Argument parsing ───────────────────────────────────────────────────────────
PROFILE="standard"
BACKEND_URL="${KYNETIC_BACKEND_URL:-https://api.kynetic.ai}"
AGENT_DIR="${KYNETIC_AGENT_DIR:-/opt/kynetic}"
INSTALL_DIR="${KYNETIC_INSTALL_DIR:-/usr/local/bin}"
DRY_RUN=false
AGENT_VERSION="${KYNETIC_AGENT_VERSION:-latest}"
UNINSTALL=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile)     PROFILE="$2";      shift 2 ;;
        --backend)     BACKEND_URL="$2";  shift 2 ;;
        --version)     AGENT_VERSION="$2"; shift 2 ;;
        --dry-run)     DRY_RUN=true;      shift   ;;
        --uninstall)   UNINSTALL=true;    shift   ;;
        --help|-h)
            echo "Usage: $0 [--profile lite|standard|gpu] [--backend URL] [--dry-run]"
            exit 0 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# ── Utilities ──────────────────────────────────────────────────────────────────
log()  { printf "\033[32m[kynetic]\033[0m %s\n" "$*"; }
warn() { printf "\033[33m[kynetic]\033[0m WARN: %s\n" "$*" >&2; }
err()  { printf "\033[31m[kynetic]\033[0m ERROR: %s\n" "$*" >&2; exit 1; }
dry()  { [[ "${DRY_RUN}" == "true" ]] && log "[DRY-RUN] $*" || true; }

ARCH="$(uname -m)"
case "${ARCH}" in
    x86_64)  ARCH_LABEL="amd64" ;;
    aarch64) ARCH_LABEL="arm64" ;;
    *) err "Unsupported architecture: ${ARCH}" ;;
esac

require_root() {
    [[ "$(id -u)" -eq 0 ]] || err "This installer must be run as root (sudo)."
}

check_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        log "Detected OS: ${PRETTY_NAME}"
    else
        warn "Could not detect OS. Proceeding anyway."
    fi
}

# ── Uninstall ──────────────────────────────────────────────────────────────────
do_uninstall() {
    log "Uninstalling Kynetic host agent..."
    [[ "${DRY_RUN}" == "true" ]] && { log "[DRY-RUN] Would uninstall"; return; }

    systemctl stop kynetic-agent 2>/dev/null || true
    systemctl disable kynetic-agent 2>/dev/null || true
    rm -f /etc/systemd/system/kynetic-agent.service
    rm -f "${INSTALL_DIR}/kynetic-agent"
    rm -rf "${AGENT_DIR}/certs" "${AGENT_DIR}/config.yaml"
    systemctl daemon-reload
    log "✓ Kynetic agent uninstalled. Data at ${AGENT_DIR} preserved."
    exit 0
}

# ── Profile size limits ────────────────────────────────────────────────────────
declare -A PROFILE_MAX_CACHE_GB=(
    [lite]="1.0"
    [standard]="5.0"
    [gpu]="5.0"
)
declare -A PROFILE_MIN_FREE_GB=(
    [lite]="5.0"
    [standard]="10.0"
    [gpu]="15.0"
)
declare -A PROFILE_LOG_MB=(
    [lite]="10"
    [standard]="25"
    [gpu]="25"
)
declare -A PROFILE_INSTALL_RUNTIME=(
    [lite]="false"     # runc only via Firecracker
    [standard]="true"  # containerd + stargz
    [gpu]="true"       # containerd + stargz + nvidia hooks
)

validate_profile() {
    case "${PROFILE}" in
        lite|standard|gpu) ;;
        *) err "Unknown profile '${PROFILE}'. Valid: lite, standard, gpu" ;;
    esac
    log "Profile: ${PROFILE}"
}

# ── Step 1: System prerequisites ───────────────────────────────────────────────
install_system_deps() {
    log "Installing system prerequisites..."
    [[ "${DRY_RUN}" == "true" ]] && { dry "apt-get install curl jq wireguard-tools"; return; }

    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        curl \
        jq \
        wireguard-tools \
        nftables \
        ca-certificates \
        systemd-timesyncd

    # Enable nftables for default-deny network isolation
    systemctl enable nftables 2>/dev/null || true

    log "  ✓ System prerequisites installed"
}

# ── Step 2: Install Firecracker + minimal kernel/rootfs ───────────────────────
install_firecracker() {
    FC_VERSION="${FIRECRACKER_VERSION:-1.8.0}"
    log "Installing Firecracker v${FC_VERSION}..."
    [[ "${DRY_RUN}" == "true" ]] && { dry "install firecracker + rootfs-min.ext4 + vmlinux-min"; return; }

    FC_TAR="firecracker-v${FC_VERSION}-${ARCH_LABEL}.tgz"
    FC_URL="https://github.com/firecracker-microvm/firecracker/releases/download/v${FC_VERSION}/${FC_TAR}"

    curl -fsSL "${FC_URL}" -o "/tmp/${FC_TAR}"
    tar -xzf "/tmp/${FC_TAR}" -C /tmp
    install -o root -g root -m 755 "/tmp/release-v${FC_VERSION}-${ARCH_LABEL}/firecracker-v${FC_VERSION}-${ARCH_LABEL}" \
        "${INSTALL_DIR}/firecracker"
    rm -rf "/tmp/${FC_TAR}" "/tmp/release-v${FC_VERSION}-${ARCH_LABEL}"

    log "  ✓ firecracker $(firecracker --version | head -1)"

    # Minimal rootfs and kernel (pre-built artefacts from rootfs_builder/)
    mkdir -p "${AGENT_DIR}"
    log "  Downloading minimal Alpine rootfs (~45 MB)..."
    curl -fsSL "https://assets.kynetic.ai/microvm/rootfs-min-${ARCH_LABEL}.ext4.zst" \
        -o "${AGENT_DIR}/rootfs-min.ext4.zst"
    zstd -d "${AGENT_DIR}/rootfs-min.ext4.zst" -o "${AGENT_DIR}/rootfs-min.ext4" --force
    rm -f "${AGENT_DIR}/rootfs-min.ext4.zst"

    log "  Downloading minimal Firecracker kernel (~12 MB)..."
    curl -fsSL "https://assets.kynetic.ai/microvm/vmlinux-min-${ARCH_LABEL}.zst" \
        -o "${AGENT_DIR}/vmlinux-min.zst"
    zstd -d "${AGENT_DIR}/vmlinux-min.zst" -o "${AGENT_DIR}/vmlinux-min" --force
    rm -f "${AGENT_DIR}/vmlinux-min.zst"

    log "  ✓ MicroVM assets installed (rootfs-min.ext4, vmlinux-min)"
}

# ── Step 3: Install container runtime (standard / gpu profiles) ────────────────
install_runtime_stack() {
    if [[ "${PROFILE_INSTALL_RUNTIME[${PROFILE}]}" != "true" ]]; then
        log "Skipping container runtime (profile=${PROFILE} — Firecracker only)"
        return
    fi

    log "Installing containerd runtime stack..."
    [[ "${DRY_RUN}" == "true" ]] && { dry "bash infra/host_install/install_runtime.sh --profile ${PROFILE}"; return; }

    # Delegate to the runtime installer
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    bash "${SCRIPT_DIR}/install_runtime.sh" --profile "${PROFILE}"
}

# ── Step 4: Install kynetic-agent binary ───────────────────────────────────────
install_agent_binary() {
    log "Installing kynetic-agent binary..."
    [[ "${DRY_RUN}" == "true" ]] && { dry "download + install kynetic-agent ~35-55 MB"; return; }

    AGENT_URL="https://assets.kynetic.ai/agent/${AGENT_VERSION}/kynetic-agent-linux-${ARCH_LABEL}"
    curl -fsSL "${AGENT_URL}" -o "/tmp/kynetic-agent"
    install -o root -g root -m 755 /tmp/kynetic-agent "${INSTALL_DIR}/kynetic-agent"
    rm -f /tmp/kynetic-agent

    log "  ✓ kynetic-agent installed at ${INSTALL_DIR}/kynetic-agent"
}

# ── Step 5: Write agent configuration ─────────────────────────────────────────
write_agent_config() {
    log "Writing agent configuration..."
    mkdir -p "${AGENT_DIR}"

    cat > "${AGENT_DIR}/config.yaml" << YAML
# Kynetic Host Agent Configuration
# Generated by install_kynetic.sh — Profile: ${PROFILE}

backend_url: "${BACKEND_URL}"
agent_dir: "${AGENT_DIR}"
install_profile: "${PROFILE}"

firecracker:
  binary: "${INSTALL_DIR}/firecracker"
  kernel_image_path: "${AGENT_DIR}/vmlinux-min"
  rootfs_path: "${AGENT_DIR}/rootfs-min.ext4"

kynetic_storage:
  permanent_base_path: "${AGENT_DIR}"
  ephemeral_workload_path: "/mnt/kynetic_nvme"
  cache:
    max_size_gb: ${PROFILE_MAX_CACHE_GB[${PROFILE}]}
    min_free_disk_gb: ${PROFILE_MIN_FREE_GB[${PROFILE}]}
    eviction_policy: "LRU"
    cleanup_interval_seconds: 600
  logging:
    max_log_size_mb: ${PROFILE_LOG_MB[${PROFILE}]}
    max_backup_files: 3
YAML

    chmod 600 "${AGENT_DIR}/config.yaml"
    log "  ✓ Config written to ${AGENT_DIR}/config.yaml"
}

# ── Step 6: Create systemd service ────────────────────────────────────────────
install_systemd_service() {
    log "Installing systemd service..."
    [[ "${DRY_RUN}" == "true" ]] && { dry "install kynetic-agent.service"; return; }

    cat > /etc/systemd/system/kynetic-agent.service << SERVICE
[Unit]
Description=Kynetic AI Host Agent (Profile: ${PROFILE})
Documentation=https://docs.kynetic.ai
After=network-online.target
Wants=network-online.target
${PROFILE_INSTALL_RUNTIME[${PROFILE}]:+After=containerd.service}

[Service]
Type=exec
ExecStart=${INSTALL_DIR}/kynetic-agent --config ${AGENT_DIR}/config.yaml
Restart=on-failure
RestartSec=10
StartLimitBurst=5
StartLimitIntervalSec=60
Environment="KYNETIC_AGENT_DIR=${AGENT_DIR}"
Environment="KYNETIC_BACKEND_URL=${BACKEND_URL}"
Environment="KYNETIC_INSTALL_PROFILE=${PROFILE}"
Environment="KYNETIC_CACHE_MAX_GB=${PROFILE_MAX_CACHE_GB[${PROFILE}]}"
Environment="KYNETIC_CACHE_MIN_FREE_GB=${PROFILE_MIN_FREE_GB[${PROFILE}]}"
Environment="KYNETIC_LOG_MAX_MB=${PROFILE_LOG_MB[${PROFILE}]}"

# Security hardening
NoNewPrivileges=false      # Agent needs root for cryptsetup / Firecracker
ProtectHome=false
ReadWritePaths=${AGENT_DIR} /mnt/kynetic_nvme /tmp /var/log/kynetic /run/containerd

[Install]
WantedBy=multi-user.target
SERVICE

    systemctl daemon-reload
    systemctl enable kynetic-agent
    systemctl start kynetic-agent
    log "  ✓ kynetic-agent.service enabled and started"
}

# ── Step 7: Verify installation ────────────────────────────────────────────────
verify() {
    log ""
    log "Verifying installation..."

    local ok=true

    if command -v kynetic-agent &>/dev/null; then
        log "  ✓ kynetic-agent: installed"
    else
        warn "  ✗ kynetic-agent: not found in PATH"
        ok=false
    fi

    if command -v firecracker &>/dev/null; then
        log "  ✓ firecracker: $(firecracker --version 2>&1 | head -1)"
    else
        warn "  ✗ firecracker: not found"
        ok=false
    fi

    if [[ -f "${AGENT_DIR}/rootfs-min.ext4" ]]; then
        rootfs_size=$(du -sh "${AGENT_DIR}/rootfs-min.ext4" | cut -f1)
        log "  ✓ rootfs-min.ext4: ${rootfs_size}"
    else
        warn "  ✗ rootfs-min.ext4: not found"
    fi

    if [[ -f "${AGENT_DIR}/vmlinux-min" ]]; then
        kernel_size=$(du -sh "${AGENT_DIR}/vmlinux-min" | cut -f1)
        log "  ✓ vmlinux-min: ${kernel_size}"
    else
        warn "  ✗ vmlinux-min: not found"
    fi

    if systemctl is-active kynetic-agent &>/dev/null; then
        log "  ✓ kynetic-agent.service: active"
    elif [[ "${DRY_RUN}" == "true" ]]; then
        log "  ~ kynetic-agent.service: (dry-run)"
    else
        warn "  ✗ kynetic-agent.service: not running"
        ok=false
    fi

    # Print total installed footprint
    total_mb=$(du -sm "${AGENT_DIR}" "${INSTALL_DIR}/kynetic-agent" "${INSTALL_DIR}/firecracker" 2>/dev/null \
        | awk '{sum += $1} END {print sum}')

    log ""
    if [[ "${ok}" == "true" ]]; then
        log "╔══════════════════════════════════════════════════════════════╗"
        log "║  ✓ Kynetic Host Agent Installed Successfully                ║"
        log "║  Profile:  ${PROFILE}$(printf '%*s' $((19 - ${#PROFILE})) '')                            ║"
        log "║  Approx permanent footprint: ~${total_mb:-???} MB                      ║"
        log "╚══════════════════════════════════════════════════════════════╝"
    else
        warn "Installation completed with warnings. Check systemctl status kynetic-agent"
    fi
}

# ── Main ───────────────────────────────────────────────────────────────────────
main() {
    require_root
    check_os

    [[ "${UNINSTALL}" == "true" ]] && do_uninstall

    validate_profile

    log "Starting Kynetic installation (profile=${PROFILE}, backend=${BACKEND_URL})"
    [[ "${DRY_RUN}" == "true" ]] && log "DRY-RUN MODE — no changes will be made"
    log ""

    install_system_deps
    install_firecracker
    install_runtime_stack
    install_agent_binary
    write_agent_config
    install_systemd_service
    verify
}

main "$@"
