package security

import (
	"fmt"
	"sync"
)

// SyscallCFIPolicy specifies allowable caller code segments for critical kernel entry points.
type SyscallCFIPolicy struct {
	SyscallNumber   uint32 `json:"syscall_number"`
	AllowedCodeBase uint64 `json:"allowed_code_base"`
	AllowedCodeLimit uint64 `json:"allowed_code_limit"`
}

// EBPFSyscallCFI enforces Forward-Edge Control Flow Integrity on system calls using kernel tracepoints.
type EBPFSyscallCFI struct {
	mu           sync.Mutex
	policies     map[uint32]SyscallCFIPolicy
	cfiViolations uint64
}

// NewEBPFSyscallCFI initializes the eBPF syscall CFI enforcer.
func NewEBPFSyscallCFI() *EBPFSyscallCFI {
	return &EBPFSyscallCFI{
		policies: make(map[uint32]SyscallCFIPolicy),
	}
}

// RegisterPolicy binds allowed caller code bounds for a specific syscall.
func (e *EBPFSyscallCFI) RegisterPolicy(policy SyscallCFIPolicy) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.policies[policy.SyscallNumber] = policy
}

// EvaluateSyscallCaller audits the Instruction Pointer (RIP/PC) of the thread making the syscall.
func (e *EBPFSyscallCFI) EvaluateSyscallCaller(syscallNum uint32, callerIP uint64) (bool, string) {
	e.mu.Lock()
	defer e.mu.Unlock()

	policy, exists := e.policies[syscallNum]
	if !exists {
		return true, "NO_CFI_POLICY_REGISTERED_PERMITTED"
	}

	if callerIP < policy.AllowedCodeBase || callerIP > policy.AllowedCodeLimit {
		e.cfiViolations++
		return false, fmt.Sprintf("CFI_FORWARD_EDGE_VIOLATION: syscall %d caller IP 0x%x outside valid text segment [0x%x, 0x%x]", syscallNum, callerIP, policy.AllowedCodeBase, policy.AllowedCodeLimit)
	}

	return true, "SYSCALL_CFI_VALIDATED"
}
