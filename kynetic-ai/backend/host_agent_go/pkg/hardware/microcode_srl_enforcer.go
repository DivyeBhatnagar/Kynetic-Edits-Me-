package hardware

import (
	"fmt"
	"sync"
)

// MicrocodeSRLEnforcer enforces CPU Security Revision Level (SRL) minimum patch levels
// to prevent microcode downgrade attacks re-opening transient execution vulnerabilities.
type MicrocodeSRLEnforcer struct {
	mu                   sync.Mutex
	minAllowedRevisions  map[string]uint32 // CPU Model/Family Signature -> Minimum Microcode Patch ID
	currentPatchVersions map[string]uint32
}

// NewMicrocodeSRLEnforcer instantiates an SRL enforcement guard.
func NewMicrocodeSRLEnforcer() *MicrocodeSRLEnforcer {
	return &MicrocodeSRLEnforcer{
		minAllowedRevisions:  make(map[string]uint32),
		currentPatchVersions: make(map[string]uint32),
	}
}

// SetMinimumSRL registers the minimum allowed microcode patch revision for a CPU family.
func (m *MicrocodeSRLEnforcer) SetMinimumSRL(cpuSignature string, minRevision uint32) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.minAllowedRevisions[cpuSignature] = minRevision
}

// AuditMicrocodeRevision evaluates the live CPU microcode patch version against the hardware SRL list.
func (m *MicrocodeSRLEnforcer) AuditMicrocodeRevision(cpuSignature string, liveRevision uint32) (bool, string) {
	m.mu.Lock()
	defer m.mu.Unlock()

	m.currentPatchVersions[cpuSignature] = liveRevision
	minReq, exists := m.minAllowedRevisions[cpuSignature]
	if !exists {
		return true, "NO_SRL_RESTRICTIONS_FOR_CPU_FAMILY"
	}

	if liveRevision < minReq {
		return false, fmt.Sprintf("MICROCODE_SRL_DOWNGRADE_BLOCKED: live revision 0x%x < minimum security revision 0x%x", liveRevision, minReq)
	}

	return true, "MICROCODE_SRL_COMPLIANT"
}
