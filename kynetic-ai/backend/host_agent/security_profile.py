"""
Host Agent — Container & Workload Security Profile Enforcer.

Enforces zero-trust isolation policies on container workloads:
  - Seccomp: Strict syscall filtering (blocking ptrace, sys_module, kexec_load, reboot)
  - AppArmor: Profile assignment ('kynetic-hardened')
  - Capabilities: Full capability drop ('cap_drop: [ALL]')
  - Privileges: Escalation prevention ('no_new_privileges: true')
  - Filesystem: Read-only root filesystem ('read_only_root_fs: true')
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ContainerSecurityProfile:
    """Dataclass carrying hardened container security parameters."""

    read_only_root_fs: bool = True
    no_new_privileges: bool = True
    cap_drop: tuple[str, ...] = ("ALL",)
    cap_add: tuple[str, ...] = ("CHOWN", "SETUID")
    apparmor_profile: str = "kynetic-hardened"
    seccomp_profile_name: str = "kynetic-seccomp.json"


SECCOMP_STRICT_SYSCALLS = [
    "ptrace",
    "kexec_load",
    "kexec_file_load",
    "sys_module",
    "init_module",
    "finit_module",
    "delete_module",
    "reboot",
    "swapon",
    "swapoff",
    "sysfs",
    "_sysctl",
    "adjtimex",
    "clock_settime",
]


def generate_seccomp_profile() -> dict:
    """Generate default strict Seccomp JSON profile."""
    return {
        "defaultAction": "SCMP_ACT_ALLOW",
        "architectures": ["SCMP_ARCH_X86_64", "SCMP_ARCH_AARCH64"],
        "syscalls": [
            {
                "names": SECCOMP_STRICT_SYSCALLS,
                "action": "SCMP_ACT_ERRNO",
                "comment": "Block kernel modification, ptrace, swap, and reboot syscalls",
            }
        ],
    }


def write_seccomp_profile(target_dir: Path) -> Path:
    """Write Seccomp profile to target directory."""
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / "kynetic-seccomp.json"
    profile = generate_seccomp_profile()
    out_path.write_text(json.dumps(profile, indent=2))
    out_path.chmod(0o644)
    logger.info("seccomp_profile_written", path=str(out_path))
    return out_path


def get_default_security_profile() -> ContainerSecurityProfile:
    """Return default hardened security profile."""
    return ContainerSecurityProfile()
