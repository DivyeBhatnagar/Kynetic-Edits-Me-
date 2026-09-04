package security

import (
	"fmt"
	"sync"
)

// SeccompNotifRequest represents an intercepted system call notification.
type SeccompNotifRequest struct {
	ID         uint64   `json:"id"`
	PID        uint32   `json:"pid"`
	SyscallNum uint32   `json:"syscall_num"`
	Args       [6]uint64 `json:"args"`
}

// SeccompNotifResponse represents the supervisor's decision on the intercepted syscall.
type SeccompNotifResponse struct {
	ID        uint64 `json:"id"`
	Allowed   bool   `json:"allowed"`
	ReturnVal int64  `json:"return_val"`
	Errno     int32  `json:"errno"`
	Reason    string `json:"reason"`
}

// SeccompUserNotifSupervisor inspects and virtualizes intercepted syscalls in userspace.
type SeccompUserNotifSupervisor struct {
	mu              sync.Mutex
	blockedSyscalls map[uint32]bool
	virtualizedCalls uint64
}

// NewSeccompUserNotifSupervisor initializes the seccomp user-notification supervisor.
func NewSeccompUserNotifSupervisor() *SeccompUserNotifSupervisor {
	return &SeccompUserNotifSupervisor{
		blockedSyscalls: make(map[uint32]bool),
	}
}

// BlockSyscall sets a hard denial rule for dangerous system calls (e.g. kexec_load, ptrace).
func (s *SeccompUserNotifSupervisor) BlockSyscall(syscallNum uint32) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.blockedSyscalls[syscallNum] = true
}

// HandleNotification evaluates an intercepted syscall request and returns a structured response.
func (s *SeccompUserNotifSupervisor) HandleNotification(req SeccompNotifRequest) SeccompNotifResponse {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.virtualizedCalls++

	if s.blockedSyscalls[req.SyscallNum] {
		return SeccompNotifResponse{
			ID:        req.ID,
			Allowed:   false,
			ReturnVal: -1,
			Errno:     1, // EPERM (Operation not permitted)
			Reason:    fmt.Sprintf("SECCOMP_USER_NOTIF_DENIED: syscall %d is blacklisted", req.SyscallNum),
		}
	}

	return SeccompNotifResponse{
		ID:        req.ID,
		Allowed:   true,
		ReturnVal: 0,
		Errno:     0,
		Reason:    "SECCOMP_USER_NOTIF_EMULATED_SUCCESS",
	}
}
