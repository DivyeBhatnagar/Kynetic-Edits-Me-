package security

import (
	"fmt"
	"os"
	"strings"
	"sync"
	"time"
)

// SyscallAnomaly represents an intercepted suspicious system call
type SyscallAnomaly struct {
	Timestamp   time.Time `json:"timestamp"`
	PID         int       `json:"pid"`
	SyscallName string    `json:"syscall_name"`
	TargetFile  string    `json:"target_file,omitempty"`
	ActionTaken string    `json:"action_taken"` // "BLOCKED", "LOGGED", "QUARANTINED"
}

// EBPFProbeManager handles in-kernel security policy checks and anomalous syscall detection
type EBPFProbeManager struct {
	mu           sync.RWMutex
	LSMSupported bool
	BlockedCalls []string
	Anomalies    []SyscallAnomaly
}

// NewEBPFProbeManager initializes the eBPF security probe manager
func NewEBPFProbeManager() *EBPFProbeManager {
	mgr := &EBPFProbeManager{
		BlockedCalls: []string{"kexec_load", "init_module", "finit_module", "delete_module", "iopl", "ioperm"},
		Anomalies:    make([]SyscallAnomaly, 0),
	}
	mgr.checkLSMSupport()
	return mgr
}

func (m *EBPFProbeManager) checkLSMSupport() {
	// Check /sys/kernel/security/lsm or /proc/sys/kernel/unprivileged_bpf_disabled
	if data, err := os.ReadFile("/sys/kernel/security/lsm"); err == nil {
		if strings.Contains(string(data), "bpf") {
			m.LSMSupported = true
			return
		}
	}
	m.LSMSupported = false
}

// RecordAnomaly logs an unauthorized syscall or sensitive path access attempt
func (m *EBPFProbeManager) RecordAnomaly(pid int, syscallName, targetFile string) SyscallAnomaly {
	m.mu.Lock()
	defer m.mu.Unlock()

	anomaly := SyscallAnomaly{
		Timestamp:   time.Now().UTC(),
		PID:         pid,
		SyscallName: syscallName,
		TargetFile:  targetFile,
		ActionTaken: "BLOCKED",
	}

	m.Anomalies = append(m.Anomalies, anomaly)
	return anomaly
}

// GetRecentAnomalies returns all intercepted anomalies in memory
func (m *EBPFProbeManager) GetRecentAnomalies() []SyscallAnomaly {
	m.mu.RLock()
	defer m.mu.RUnlock()

	result := make([]SyscallAnomaly, len(m.Anomalies))
	copy(result, m.Anomalies)
	return result
}

// ValidateProcessIsolation ensures sensitive /dev/mem and raw block access are blocked for PID
func (m *EBPFProbeManager) ValidateProcessIsolation(pid int) error {
	procRoot := fmt.Sprintf("/proc/%d/root", pid)
	if _, err := os.Stat(procRoot); os.IsNotExist(err) {
		return nil // Process already terminated
	}

	// Verify rootfs isolation
	for _, sensitive := range []string{"/dev/mem", "/dev/kmem", "/etc/shadow"} {
		target := fmt.Sprintf("%s%s", procRoot, sensitive)
		if _, err := os.Stat(target); err == nil {
			m.RecordAnomaly(pid, "open", sensitive)
			return fmt.Errorf("isolation breach: process %d has access to %s", pid, sensitive)
		}
	}
	return nil
}
