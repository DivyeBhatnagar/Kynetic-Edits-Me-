package hardware

import (
	"fmt"
	"sync"
)

// ATSTranslationRequest represents a PCIe / InfiniBand Address Translation Service query.
type ATSTranslationRequest struct {
	DeviceBDF       string `json:"device_bdf"` // Bus:Device.Function
	RequestedVAddr  uint64 `json:"requested_vaddr"`
	TranslatedPAddr uint64 `json:"translated_paddr"`
	IsWriteRequest  bool   `json:"is_write_request"`
}

// ATSSpoofGuard audits PCIe Address Translation Services to prevent peripheral DMA address spoofing.
type ATSSpoofGuard struct {
	mu            sync.Mutex
	trustedDevices map[string]bool
	allowedPAddrMin uint64
	allowedPAddrMax uint64
	violationsCount uint64
}

// NewATSSpoofGuard constructs an ATS spoofing validator.
func NewATSSpoofGuard(pAddrMin, pAddrMax uint64) *ATSSpoofGuard {
	return &ATSSpoofGuard{
		trustedDevices:  make(map[string]bool),
		allowedPAddrMin: pAddrMin,
		allowedPAddrMax: pAddrMax,
	}
}

// RegisterTrustedDevice grants ATS caching capability to an authenticated PCIe GPU/HCA device.
func (a *ATSSpoofGuard) RegisterTrustedDevice(deviceBDF string) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.trustedDevices[deviceBDF] = true
}

// ValidateATSResponse audits the translated physical address against IOMMU aperture bounds.
func (a *ATSSpoofGuard) ValidateATSResponse(req ATSTranslationRequest) (bool, string) {
	a.mu.Lock()
	defer a.mu.Unlock()

	if !a.trustedDevices[req.DeviceBDF] {
		a.violationsCount++
		return false, fmt.Sprintf("UNTRUSTED_DEVICE_ATS_REJECTED: %s not in ATS whitelist", req.DeviceBDF)
	}

	if req.TranslatedPAddr < a.allowedPAddrMin || req.TranslatedPAddr > a.allowedPAddrMax {
		a.violationsCount++
		return false, fmt.Sprintf("ATS_TRANSLATION_OUT_OF_BOUNDS: pAddr 0x%x outside [0x%x, 0x%x]", req.TranslatedPAddr, a.allowedPAddrMin, a.allowedPAddrMax)
	}

	return true, "ATS_TRANSLATION_VALIDATED"
}
