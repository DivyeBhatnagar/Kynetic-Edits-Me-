package hardware

import (
	"fmt"
	"sync"
)

// SEVvTOMStatus holds AMD SEV-SNP Virtual Top of Memory and Reverse Map Table state.
type SEVvTOMStatus struct {
	VTOMAddressHex string `json:"vtom_address_hex"`
	RMPEnforced    bool   `json:"rmp_enforced"`
	VMSAChecksum   string `json:"vmsa_checksum"`
	SplicingAlerts []string `json:"splicing_alerts"`
}

// SEVvTOMGuard protects confidential guest memory from hypervisor splicing attacks.
type SEVvTOMGuard struct {
	mu           sync.Mutex
	vtomBoundary uint64
	rmpEnabled   bool
	vmsaDigest   string
	alerts       []string
}

// NewSEVvTOMGuard instantiates an AMD SEV-SNP vTOM memory protection guard.
func NewSEVvTOMGuard(vtomBoundary uint64, initialVMSADigest string) *SEVvTOMGuard {
	return &SEVvTOMGuard{
		vtomBoundary: vtomBoundary,
		rmpEnabled:   true,
		vmsaDigest:   initialVMSADigest,
		alerts:       make([]string, 0),
	}
}

// AuditMemoryAccess verifies that private guest memory is above/below vTOM as mandated by AMD SEV-SNP architecture.
func (s *SEVvTOMGuard) AuditMemoryAccess(physicalAddress uint64, isPrivateExpected bool) (bool, string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	isPrivateActual := physicalAddress < s.vtomBoundary

	if isPrivateExpected && !isPrivateActual {
		alert := fmt.Sprintf("HYPERVISOR_SPLICING_ATTEMPT: address 0x%x is above vTOM boundary 0x%x (shared memory space)", physicalAddress, s.vtomBoundary)
		s.alerts = append(s.alerts, alert)
		return false, alert
	}

	if !isPrivateExpected && isPrivateActual {
		alert := fmt.Sprintf("UNAUTHORIZED_SHARED_ACCESS_IN_PRIVATE_PAGE: address 0x%x below vTOM 0x%x", physicalAddress, s.vtomBoundary)
		s.alerts = append(s.alerts, alert)
		return false, alert
	}

	return true, "SEV_SNP_VTOM_ACCESS_VALID"
}

// VerifyVMSAChecksum verifies that the Virtual Machine Save Area has not been altered by the untrusted hypervisor.
func (s *SEVvTOMGuard) VerifyVMSAChecksum(currentVMSADigest string) (bool, string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.vmsaDigest != currentVMSADigest {
		alert := fmt.Sprintf("VMSA_INTEGRITY_TAMPER_DETECTED: expected %s, got %s", s.vmsaDigest, currentVMSADigest)
		s.alerts = append(s.alerts, alert)
		return false, alert
	}

	return true, "VMSA_STATE_INTACT"
}
