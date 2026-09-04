package security

import (
	"os"
	"strings"
)

// IMAStatus represents the Linux Integrity Measurement Architecture status
type IMAStatus struct {
	IMAActive       bool   `json:"ima_active"`
	AppraisalMode   string `json:"appraisal_mode"` // "enforce", "log", "off"
	SecureBootActive bool  `json:"secure_boot_active"`
	RuntimeTampered bool   `json:"runtime_tampered"`
}

// CheckIMAAndSecureBoot inspects kernel security and EFI variables for Secure Boot & IMA
func CheckIMAAndSecureBoot() *IMAStatus {
	status := &IMAStatus{
		AppraisalMode: "off",
	}

	// 1. Check IMA policy in sysfs
	if _, err := os.Stat("/sys/kernel/security/ima/policy"); err == nil {
		status.IMAActive = true
		status.AppraisalMode = "enforce"
	}

	// 2. Check EFI Secure Boot
	// Path /sys/firmware/efi/efivars/SecureBoot-*
	if _, err := os.Stat("/sys/firmware/efi/efivars"); err == nil {
		entries, _ := os.ReadDir("/sys/firmware/efi/efivars")
		for _, e := range entries {
			if strings.HasPrefix(e.Name(), "SecureBoot-") {
				if data, err := os.ReadFile("/sys/firmware/efi/efivars/" + e.Name()); err == nil {
					// 5th byte holds the active value (1 = Enabled)
					if len(data) >= 5 && data[4] == 1 {
						status.SecureBootActive = true
					}
				}
				break
			}
		}
	}

	return status
}
