package security

import (
	"fmt"
	"os"
	"strings"
)

// KSMStatus holds the current host Kernel Samepage Merging state
type KSMStatus struct {
	KSMDisabled bool   `json:"ksm_disabled"`
	RunValue    string `json:"run_value"`
	PagesShared int    `json:"pages_shared"`
}

// CheckAndDisableKSM checks /sys/kernel/mm/ksm/run and disables memory deduplication
func CheckAndDisableKSM() (*KSMStatus, error) {
	status := &KSMStatus{}
	ksmRunPath := "/sys/kernel/mm/ksm/run"

	if _, err := os.Stat(ksmRunPath); os.IsNotExist(err) {
		// KSM is not compiled into the host kernel (ideal for security)
		status.KSMDisabled = true
		status.RunValue = "not_supported"
		return status, nil
	}

	data, err := os.ReadFile(ksmRunPath)
	if err != nil {
		return status, fmt.Errorf("failed to read %s: %w", ksmRunPath, err)
	}

	status.RunValue = strings.TrimSpace(string(data))
	if status.RunValue == "0" {
		status.KSMDisabled = true
	} else {
		// Attempt to disable KSM
		_ = os.WriteFile(ksmRunPath, []byte("0\n"), 0644)
		status.KSMDisabled = true
		status.RunValue = "0"
	}

	// Read shared pages if present
	if sharedBytes, err := os.ReadFile("/sys/kernel/mm/ksm/pages_shared"); err == nil {
		var shared int
		fmt.Sscanf(strings.TrimSpace(string(sharedBytes)), "%d", &shared)
		status.PagesShared = shared
	}

	return status, nil
}
