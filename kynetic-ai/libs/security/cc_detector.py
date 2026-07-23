"""
Phase 19 — Hardware Root-of-Trust Detection & Tier Classification
Inspects host CPU, GPU, TPM 2.0, and IOMMU groups to determine security tier:
  - 'confidential_tier': AMD SEV-SNP / Intel TDX + NVIDIA Hopper CC mode
  - 'standard_tier': VFIO IOMMU isolation + Firecracker MicroVM
"""

import subprocess
import os
from typing import Dict, Any


class HardwareSecurityReport:
    def __init__(self):
        self.sev_snp: bool = False
        self.intel_tdx: bool = False
        self.nvidia_cc: bool = False
        self.tpm_present: bool = False
        self.iommu_enabled: bool = False
        self.gpu_model: str = "Unknown"

    @property
    def determined_tier(self) -> str:
        if (self.sev_snp or self.intel_tdx) and self.nvidia_cc and self.tpm_present:
            return "confidential_tier"
        return "standard_tier"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sev_snp": self.sev_snp,
            "intel_tdx": self.intel_tdx,
            "nvidia_cc": self.nvidia_cc,
            "tpm_present": self.tpm_present,
            "iommu_enabled": self.iommu_enabled,
            "gpu_model": self.gpu_model,
            "determined_tier": self.determined_tier,
        }


def inspect_host_security_capabilities() -> HardwareSecurityReport:
    report = HardwareSecurityReport()

    # 1. CPU SEV-SNP / TDX check
    try:
        if os.path.exists("/sys/module/kvm_amd/parameters/sev_snp"):
            with open("/sys/module/kvm_amd/parameters/sev_snp") as f:
                report.sev_snp = f.read().strip() in ("1", "Y", "y")
        if os.path.exists("/sys/module/kvm_intel/parameters/tdx"):
            with open("/sys/module/kvm_intel/parameters/tdx") as f:
                report.intel_tdx = f.read().strip() in ("1", "Y", "y")
    except Exception:
        pass

    # 2. TPM 2.0 Presence
    report.tpm_present = os.path.exists("/dev/tpm0") or os.path.exists("/dev/tpmrm0")

    # 3. IOMMU Groups Check
    report.iommu_enabled = os.path.exists("/sys/kernel/iommu_groups") and len(os.listdir("/sys/kernel/iommu_groups")) > 0

    # 4. GPU NVML & CC Mode check
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        report.gpu_model = pynvml.nvmlDeviceGetName(handle)
        if any(chip in report.gpu_model for chip in ["H100", "H200", "B100", "B200"]):
            out = subprocess.run(["nvidia-smi", "conf-compute", "-f"], capture_output=True, text=True, timeout=3).stdout
            report.nvidia_cc = "ENABLED" in out.upper()
    except Exception:
        pass

    return report
