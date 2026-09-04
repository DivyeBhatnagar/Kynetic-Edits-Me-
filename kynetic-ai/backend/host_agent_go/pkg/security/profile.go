// Package security writes the Seccomp and AppArmor hardening profiles.
//
// Replaces: backend/host_agent/security_profile.py
package security

import (
	"encoding/json"
	"os"
	"path/filepath"
)

// SeccompProfile defines the strict Kynetic container syscall filter.
// Blocks dangerous kernel operations: ptrace, kexec, sys_module, reboot, swap.
type SeccompProfile struct {
	DefaultAction string          `json:"defaultAction"`
	Architectures []string        `json:"architectures"`
	Syscalls      []SyscallFilter `json:"syscalls"`
}

// SyscallFilter defines a list of blocked syscalls and the action to take.
type SyscallFilter struct {
	Names   []string `json:"names"`
	Action  string   `json:"action"`
	Comment string   `json:"comment,omitempty"`
}

var blockedSyscalls = []string{
	"ptrace", "kexec_load", "kexec_file_load",
	"init_module", "finit_module", "delete_module",
	"reboot", "swapon", "swapoff",
	"sysfs", "_sysctl", "adjtimex", "clock_settime",
}

// GenerateSeccompProfile returns the hardened Seccomp profile for Kynetic containers.
func GenerateSeccompProfile() SeccompProfile {
	return SeccompProfile{
		DefaultAction: "SCMP_ACT_ALLOW",
		Architectures: []string{"SCMP_ARCH_X86_64", "SCMP_ARCH_AARCH64"},
		Syscalls: []SyscallFilter{
			{
				Names:   blockedSyscalls,
				Action:  "SCMP_ACT_ERRNO",
				Comment: "Block kernel modification, ptrace, swap, and reboot syscalls",
			},
		},
	}
}

// WriteSeccompProfile writes kynetic-seccomp.json to targetDir.
func WriteSeccompProfile(targetDir string) error {
	if err := os.MkdirAll(targetDir, 0755); err != nil {
		return err
	}
	profile := GenerateSeccompProfile()
	data, err := json.MarshalIndent(profile, "", "  ")
	if err != nil {
		return err
	}
	outPath := filepath.Join(targetDir, "kynetic-seccomp.json")
	if err := os.WriteFile(outPath, data, 0644); err != nil {
		return err
	}
	return nil
}

// ContainerSecurityProfile holds hardened container execution flags.
// Used when constructing containerd task spec.
type ContainerSecurityProfile struct {
	ReadOnlyRootFS   bool
	NoNewPrivileges  bool
	CapDrop          []string
	CapAdd           []string
	AppArmorProfile  string
	SeccompProfile   string
}

// DefaultProfile returns the hardened execution profile for all Kynetic workloads.
func DefaultProfile() ContainerSecurityProfile {
	return ContainerSecurityProfile{
		ReadOnlyRootFS:  true,
		NoNewPrivileges: true,
		CapDrop:         []string{"ALL"},
		CapAdd:          []string{"CHOWN", "SETUID"},
		AppArmorProfile: "kynetic-hardened",
		SeccompProfile:  "/etc/kynetic/kynetic-seccomp.json",
	}
}
