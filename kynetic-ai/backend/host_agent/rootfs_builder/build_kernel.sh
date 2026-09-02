#!/usr/bin/env bash
# Phase 2 — Kynetic MicroVM Minimal Kernel Builder
#
# Builds a Firecracker-optimised Linux kernel (~12 MB stripped vmlinux)
# from the latest LTS kernel source, replacing the unstripped full kernel (~35 MB).
#
# Key kernel config principles:
#   - Enable ONLY Firecracker-required virtio drivers
#   - Disable all legacy hardware drivers (PCI, USB, ACPI, legacy IRQ)
#   - Disable all non-virtio network adapters
#   - Disable kernel modules (all drivers compiled in or off — no module loading)
#   - Disable debug infrastructure (KASAN, KCOV, lockdep, etc.)
#   - Strip the final vmlinux binary
#
# Prerequisites:
#   - Linux build environment (not macOS)
#   - apt-get install build-essential bison flex libssl-dev libelf-dev bc
#
# Usage:
#   bash backend/host_agent/rootfs_builder/build_kernel.sh
#   → Produces /opt/kynetic/vmlinux-min (~12 MB)
#
# Reference config based on Firecracker's recommended microvm kernel config:
#   https://github.com/firecracker-microvm/firecracker/blob/main/resources/guest_configs/

set -euo pipefail

KERNEL_VERSION="${KERNEL_VERSION:-6.1.90}"
KERNEL_TARBALL="linux-${KERNEL_VERSION}.tar.xz"
KERNEL_URL="https://cdn.kernel.org/pub/linux/kernel/v6.x/${KERNEL_TARBALL}"
BUILD_DIR="${BUILD_DIR:-/tmp/kynetic-kernel-build}"
OUTPUT_DIR="${OUTPUT_DIR:-/opt/kynetic}"
JOBS="${JOBS:-$(nproc)}"

log() { echo "[kynetic-kernel] $*"; }

# ── Download kernel source ─────────────────────────────────────────────────────
mkdir -p "${BUILD_DIR}"
cd "${BUILD_DIR}"

if [[ ! -f "${KERNEL_TARBALL}" ]]; then
    log "Downloading Linux ${KERNEL_VERSION}..."
    curl -fSL "${KERNEL_URL}" -o "${KERNEL_TARBALL}"
fi

if [[ ! -d "linux-${KERNEL_VERSION}" ]]; then
    log "Extracting..."
    tar -xf "${KERNEL_TARBALL}"
fi

cd "linux-${KERNEL_VERSION}"

# ── Apply minimal Firecracker microVM kernel config ────────────────────────────
log "Configuring minimal Firecracker kernel..."

# Start from a completely empty config
make mrproper

cat > .config << 'KERNEL_CONFIG'
# ─── Core ──────────────────────────────────────────────────────────────────────
CONFIG_64BIT=y
CONFIG_SMP=y
CONFIG_NR_CPUS=32
CONFIG_MODULES=n                     # No module support — all in-kernel or off
CONFIG_PREEMPT_NONE=y
CONFIG_HZ_250=y

# ─── Memory ────────────────────────────────────────────────────────────────────
CONFIG_TRANSPARENT_HUGEPAGE=y
CONFIG_TRANSPARENT_HUGEPAGE_ALWAYS=y
CONFIG_MEMCG=y

# ─── Virtio (Firecracker uses virtio for all I/O) ──────────────────────────────
CONFIG_VIRTIO=y
CONFIG_VIRTIO_PCI=n                  # Firecracker uses MMIO, not PCI
CONFIG_VIRTIO_MMIO=y
CONFIG_VIRTIO_NET=y
CONFIG_VIRTIO_BLK=y
CONFIG_VIRTIO_VSOCK=y
CONFIG_VHOST_NET=n
CONFIG_NET_9P_VIRTIO=n

# ─── Network ───────────────────────────────────────────────────────────────────
CONFIG_NET=y
CONFIG_INET=y
CONFIG_IPV6=n
CONFIG_NETFILTER=n
CONFIG_BRIDGE=n
CONFIG_PACKET=y
CONFIG_UNIX=y
# No legacy NICs
CONFIG_E1000=n
CONFIG_E1000E=n
CONFIG_VMXNET3=n
CONFIG_TULIP=n

# ─── Block / Storage ───────────────────────────────────────────────────────────
CONFIG_EXT4_FS=y
CONFIG_OVERLAY_FS=y                  # For read-only rootfs + overlay mounts
CONFIG_TMPFS=y
CONFIG_PROC_FS=y
CONFIG_SYSFS=y
CONFIG_DEVTMPFS=y
# No legacy storage drivers
CONFIG_ATA=n
CONFIG_SCSI=n
CONFIG_NVMe=n                        # Host NVMe exposed as virtio-blk to guest
CONFIG_USB_STORAGE=n
CONFIG_MMC=n

# ─── Crypto (for LUKS2 / WireGuard) ───────────────────────────────────────────
CONFIG_CRYPTO=y
CONFIG_CRYPTO_AES=y
CONFIG_CRYPTO_XTS=y
CONFIG_CRYPTO_SHA512=y
CONFIG_CRYPTO_ARGON2=y
CONFIG_WIREGUARD=y

# ─── Serial console (Firecracker uses ttyS0) ──────────────────────────────────
CONFIG_SERIAL_8250=y
CONFIG_SERIAL_8250_CONSOLE=y
CONFIG_TTY=y

# ─── Disable legacy hardware drivers (major size reducers) ─────────────────────
CONFIG_PCI=n
CONFIG_PCIEPORTBUS=n
CONFIG_PCI_MSI=n
CONFIG_ACPI=n
CONFIG_X86_ACPI_CPUFREQ=n
CONFIG_USB=n
CONFIG_SOUND=n
CONFIG_DRM=n
CONFIG_GPU_DRM=n
CONFIG_FRAMEBUFFER_CONSOLE=n
CONFIG_HID=n
CONFIG_INPUT=n
CONFIG_SERIO=n
CONFIG_GAMEPORT=n
CONFIG_INFINIBAND=n
CONFIG_ISDN=n
CONFIG_ATM=n
CONFIG_BLUETOOTH=n
CONFIG_WIRELESS=n
CONFIG_CFG80211=n
CONFIG_MAC80211=n

# ─── Disable debug / tracing infrastructure ────────────────────────────────────
CONFIG_DEBUG_KERNEL=n
CONFIG_DEBUG_INFO=n
CONFIG_KASAN=n
CONFIG_KCOV=n
CONFIG_LOCKDEP=n
CONFIG_TRACE_IRQFLAGS=n
CONFIG_FTRACE=n
CONFIG_PERF_EVENTS=n
CONFIG_SLUB_DEBUG=n
CONFIG_KPROBES=n
CONFIG_LKDTM=n
CONFIG_KALLSYMS=n

# ─── Misc ──────────────────────────────────────────────────────────────────────
CONFIG_BINFMT_ELF=y
CONFIG_BINFMT_SCRIPT=y
CONFIG_COREDUMP=n
CONFIG_CHECKPOINT_RESTORE=n
CONFIG_NAMESPACES=y
CONFIG_PID_NS=y
CONFIG_NET_NS=y
CONFIG_UTS_NS=y
CONFIG_IPC_NS=y
CONFIG_USER_NS=y
CONFIG_CGROUPS=y
CONFIG_CGROUP_CPUACCT=y
CONFIG_CGROUP_DEVICE=y
CONFIG_CGROUP_FREEZER=y
CONFIG_CGROUP_NET_CLASSID=n
CONFIG_CGROUP_SCHED=y
CONFIG_CPUSETS=y
CONFIG_MEMCG=y
CONFIG_SECCOMP=y
CONFIG_SECCOMP_FILTER=y
KERNEL_CONFIG

# Resolve any missing symbols to their defaults
make olddefconfig

# ── Build ──────────────────────────────────────────────────────────────────────
log "Building kernel with -j${JOBS}..."
make -j"${JOBS}" vmlinux

# ── Strip and install ──────────────────────────────────────────────────────────
log "Stripping vmlinux..."
strip --strip-debug vmlinux -o vmlinux-stripped

FINAL_SIZE=$(du -sh vmlinux-stripped | cut -f1)
log "Stripped kernel size: ${FINAL_SIZE}"

mkdir -p "${OUTPUT_DIR}"
cp vmlinux-stripped "${OUTPUT_DIR}/vmlinux-min"
chmod 644 "${OUTPUT_DIR}/vmlinux-min"

log "✓ Kernel installed at ${OUTPUT_DIR}/vmlinux-min (${FINAL_SIZE})"
log "  Use kernel_image_path=\"${OUTPUT_DIR}/vmlinux-min\" in firecracker.py"
