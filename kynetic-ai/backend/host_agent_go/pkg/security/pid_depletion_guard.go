package security

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"go.uber.org/zap"
)

// PIDDepletionGuard detects rapid process exhaustion attacks and enforces quarantine cool-down windows on recycled PIDs.
type PIDDepletionGuard struct {
	logger        *zap.Logger
	pidMaxPath    string
	mu            sync.Mutex
	cooldown      time.Duration
	tombstones    map[int]time.Time
	configuredMax int
}

// NewPIDDepletionGuard initializes the PID exhaustion and recycling guard.
func NewPIDDepletionGuard(logger *zap.Logger, customPidMax string, cooldown time.Duration) *PIDDepletionGuard {
	if customPidMax == "" {
		customPidMax = "/proc/sys/kernel/pid_max"
	}
	if cooldown <= 0 {
		cooldown = 2 * time.Second
	}
	return &PIDDepletionGuard{
		logger:        logger,
		pidMaxPath:    customPidMax,
		cooldown:      cooldown,
		tombstones:    make(map[int]time.Time),
		configuredMax: 4194304, // Modern 64-bit Linux PID max
	}
}

// AuditPIDCapacity checks /proc/sys/kernel/pid_max and flags if PID space is dangerously constrained (< 65536).
func (g *PIDDepletionGuard) AuditPIDCapacity() (int, bool, error) {
	g.mu.Lock()
	defer g.mu.Unlock()

	data, err := os.ReadFile(g.pidMaxPath)
	if err != nil {
		if os.IsNotExist(err) {
			// Mock environment (Darwin / CI)
			return g.configuredMax, true, nil
		}
		return 0, false, fmt.Errorf("failed to read pid_max: %w", err)
	}

	valStr := strings.TrimSpace(string(data))
	val, err := strconv.Atoi(valStr)
	if err != nil {
		return 0, false, err
	}

	g.configuredMax = val
	isSafe := val >= 65536
	if !isSafe {
		g.logger.Warn("PIDDepletionGuard: kernel pid_max is dangerously low, risk of PID recycling race condition",
			zap.Int("pid_max", val),
		)
	}

	return val, isSafe, nil
}

// MarkTerminatedPID registers a terminated PID into the tombstone quarantine list.
func (g *PIDDepletionGuard) MarkTerminatedPID(pid int) {
	g.mu.Lock()
	defer g.mu.Unlock()
	g.tombstones[pid] = time.Now()
}

// IsPIDQuarantined checks if a newly allocated PID was terminated too recently to safely reuse.
func (g *PIDDepletionGuard) IsPIDQuarantined(pid int) bool {
	g.mu.Lock()
	defer g.mu.Unlock()

	ts, exists := g.tombstones[pid]
	if !exists {
		return false
	}

	if time.Since(ts) < g.cooldown {
		return true
	}

	delete(g.tombstones, pid)
	return false
}
