"""
Phase v5 — Layer 2: gVisor Application Kernel Sandbox Configurator
Configures Google gVisor (runsc) user-space kernel sandbox inside Firecracker MicroVM.
Generates seccomp-BPF filters blocking raw host Linux system call execution.
"""

from typing import Dict, Any, List


class GVisorSandboxPolicy:
    """
    gVisor (runsc) sandbox configuration generator.
    Enforces user-space system call interception.
    """
    FORBIDDEN_SYSCALLS: List[str] = [
        "ptrace",
        "process_vm_readv",
        "process_vm_writev",
        "kexec_load",
        "bpf",
        "userfaultfd",
        "perf_event_open",
    ]

    @classmethod
    def generate_gvisor_config(cls, container_id: str) -> Dict[str, Any]:
        return {
            "runtime": "runsc",
            "container_id": container_id,
            "platform": "systrap",
            "overlay": "memory",
            "seccomp": {
                "defaultAction": "SCMP_ACT_ERRNO",
                "forbidden_syscalls": cls.FORBIDDEN_SYSCALLS,
            },
            "network": "sandboxed",
        }

    @classmethod
    def is_syscall_permitted(cls, syscall_name: str) -> bool:
        return syscall_name not in cls.FORBIDDEN_SYSCALLS
