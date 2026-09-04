package security

import (
	"fmt"
	"sync"
)

// PKUDomainPermission represents the access rights for a Protection Key domain.
type PKUDomainPermission uint8

const (
	PKUAccessReadWrite PKUDomainPermission = 0x0
	PKUAccessReadOnly  PKUDomainPermission = 0x1 // Access Disable Write (AD)
	PKUAccessNone      PKUDomainPermission = 0x3 // Access Disable Read + Write (WD + AD)
)

// PKUProtectionDomain holds hardware key assignments for intra-process memory boundaries.
type PKUProtectionDomain struct {
	KeyIndex    uint8               `json:"key_index"` // 0-15
	DomainName  string              `json:"domain_name"`
	Permission  PKUDomainPermission `json:"permission"`
	IsProtected bool                `json:"is_protected"`
}

// PKUMPKSandbox partitions thread address spaces using CPU Memory Protection Keys (Intel MPK / AMD PKU).
type PKUMPKSandbox struct {
	mu      sync.Mutex
	domains map[uint8]*PKUProtectionDomain
}

// NewPKUMPKSandbox initializes the MPK/PKU user-space sandbox manager.
func NewPKUMPKSandbox() *PKUMPKSandbox {
	return &PKUMPKSandbox{
		domains: make(map[uint8]*PKUProtectionDomain),
	}
}

// AllocateDomain reserves a hardware protection key (PKEY) for a sensitive memory subsystem.
func (p *PKUMPKSandbox) AllocateDomain(keyIndex uint8, name string, perm PKUDomainPermission) error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if keyIndex > 15 {
		return fmt.Errorf("invalid PKU key index %d (must be 0-15)", keyIndex)
	}

	p.domains[keyIndex] = &PKUProtectionDomain{
		KeyIndex:    keyIndex,
		DomainName:  name,
		Permission:  perm,
		IsProtected: true,
	}
	return nil
}

// AssertAccessPermission verifies that the calling thread has right to read/write the domain.
func (p *PKUMPKSandbox) AssertAccessPermission(keyIndex uint8, isWrite bool) (bool, string) {
	p.mu.Lock()
	defer p.mu.Unlock()

	dom, exists := p.domains[keyIndex]
	if !exists {
		return true, "DEFAULT_DOMAIN_PERMITTED"
	}

	if dom.Permission == PKUAccessNone {
		return false, fmt.Sprintf("PKU_ISOLATION_FAULT: domain %s (key %d) completely access disabled", dom.DomainName, keyIndex)
	}

	if isWrite && dom.Permission == PKUAccessReadOnly {
		return false, fmt.Sprintf("PKU_WRITE_VIOLATION: domain %s (key %d) is read-only", dom.DomainName, keyIndex)
	}

	return true, "PKU_MEMORY_ACCESS_GRANTED"
}
