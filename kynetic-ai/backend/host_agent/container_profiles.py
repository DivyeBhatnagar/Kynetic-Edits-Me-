"""
Host Agent — Container Security Profiles (Part 12).

Defines STANDARD, HARDENED, and VERIFIED workload security profiles for Docker/Firecracker execution:
- STANDARD: Default Docker seccomp/AppArmor, dropped non-essential capabilities, no-new-privileges set.
- HARDENED: Restrictive custom seccomp profile, read-only root FS, workspace read-write only.
- VERIFIED: HARDENED + TPM 2.0 hardware attestation requirement (Part 5).
"""

import enum
from dataclasses import dataclass, field
import structlog

log = structlog.get_logger(__name__)


class SecurityProfileTier(str, enum.Enum):
    STANDARD = "STANDARD"
    HARDENED = "HARDENED"
    VERIFIED = "VERIFIED"
    CONFIDENTIAL = "CONFIDENTIAL"


@dataclass
class ContainerSecurityProfile:
    tier: SecurityProfileTier
    seccomp_profile: str            # 'default' or path to restrictive seccomp json
    apparmor_profile: str           # 'docker-default' or 'kynetic-hardened'
    read_only_root_fs: bool
    no_new_privileges: bool
    cap_drop: list[str] = field(default_factory=lambda: ["ALL"])
    cap_add: list[str] = field(default_factory=list)


PROFILES = {
    SecurityProfileTier.STANDARD: ContainerSecurityProfile(
        tier=SecurityProfileTier.STANDARD,
        seccomp_profile="default",
        apparmor_profile="docker-default",
        read_only_root_fs=False,
        no_new_privileges=True,
        cap_drop=["SYS_ADMIN", "NET_ADMIN", "SYS_RAWIO", "SYS_PTRACE"],
    ),
    SecurityProfileTier.HARDENED: ContainerSecurityProfile(
        tier=SecurityProfileTier.HARDENED,
        seccomp_profile="/opt/kynetic/seccomp_hardened.json",
        apparmor_profile="kynetic-hardened",
        read_only_root_fs=True,
        no_new_privileges=True,
        cap_drop=["ALL"],
        cap_add=["CHOWN", "SETUID", "SETGID"],
    ),
    SecurityProfileTier.VERIFIED: ContainerSecurityProfile(
        tier=SecurityProfileTier.VERIFIED,
        seccomp_profile="/opt/kynetic/seccomp_hardened.json",
        apparmor_profile="kynetic-hardened",
        read_only_root_fs=True,
        no_new_privileges=True,
        cap_drop=["ALL"],
        cap_add=["CHOWN", "SETUID", "SETGID"],
    ),
}


def get_security_profile(tier: SecurityProfileTier = SecurityProfileTier.STANDARD) -> ContainerSecurityProfile:
    """Returns the ContainerSecurityProfile configuration for the specified tier."""
    profile = PROFILES.get(tier, PROFILES[SecurityProfileTier.STANDARD])
    log.debug("container_profile.selected", tier=tier.value, read_only=profile.read_only_root_fs)
    return profile
