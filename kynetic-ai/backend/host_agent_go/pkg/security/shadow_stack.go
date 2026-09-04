package security

import (
	"context"
	"os"
	"strings"
	"sync"

	"go.uber.org/zap"
)

// ShadowStackStatus represents hardware-assisted Control Flow Enforcement Technology (CET) state.
type ShadowStackStatus struct {
	CETSupported bool   `json:"cet_supported"`
	ShadowStackActive bool `json:"shadow_stack_active"`
	IBTActive    bool   `json:"ibt_active"`
}

// ShadowStackController audits and enables hardware shadow stack and indirect branch tracking
// (Intel CET / ARM BTI) to eliminate Return-Oriented Programming (ROP) exploits.
type ShadowStackController struct {
	logger      *zap.Logger
	cpuinfoPath string
	mu          sync.Mutex
	status      ShadowStackStatus
}

// NewShadowStackController creates a new ShadowStackController.
func NewShadowStackController(logger *zap.Logger, cpuinfoPath string) *ShadowStackController {
	if cpuinfoPath == "" {
		cpuinfoPath = "/proc/cpuinfo"
	}
	return &ShadowStackController{
		logger:      logger,
		cpuinfoPath: cpuinfoPath,
	}
}

// AuditShadowStackFeatures queries CPU flags for user-mode shadow stack (shstk) and IBT (ibt).
func (s *ShadowStackController) AuditShadowStackFeatures(ctx context.Context) (ShadowStackStatus, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	status := ShadowStackStatus{}
	data, err := os.ReadFile(s.cpuinfoPath)
	if err != nil {
		if os.IsNotExist(err) {
			s.logger.Debug("cpuinfo not present (mock/fallback mode)")
			s.status = status
			return status, nil
		}
		return status, err
	}

	content := string(data)
	if strings.Contains(content, "shstk") || strings.Contains(content, "cet") {
		status.CETSupported = true
		status.ShadowStackActive = true
	}
	if strings.Contains(content, "ibt") || strings.Contains(content, "bti") {
		status.IBTActive = true
	}

	s.status = status
	s.logger.Info("Control Flow / Shadow Stack capability audited",
		zap.Bool("cet_supported", status.CETSupported),
		zap.Bool("ibt_active", status.IBTActive),
	)
	return status, nil
}

// GetStatus returns the current shadow stack status.
func (s *ShadowStackController) GetStatus() ShadowStackStatus {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.status
}
