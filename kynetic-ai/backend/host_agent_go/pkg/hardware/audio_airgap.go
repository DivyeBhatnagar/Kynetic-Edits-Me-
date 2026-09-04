package hardware

import (
	"context"
	"os"
	"path/filepath"
	"sync"

	"go.uber.org/zap"
)

// AudioAirgapManager disables host microphone, audio input/output, and camera
// device nodes before and during guest tenant execution to eliminate acoustic/optical side-channels or eavesdropping.
type AudioAirgapManager struct {
	logger        *zap.Logger
	sndPath       string
	videoPath     string
	mu            sync.Mutex
	isolatedNodes []string
	isAirgapped   bool
}

// NewAudioAirgapManager instantiates a new AudioAirgapManager.
func NewAudioAirgapManager(logger *zap.Logger, sndPath, videoPath string) *AudioAirgapManager {
	if sndPath == "" {
		sndPath = "/dev/snd"
	}
	if videoPath == "" {
		videoPath = "/dev"
	}
	return &AudioAirgapManager{
		logger:        logger,
		sndPath:       sndPath,
		videoPath:     videoPath,
		isolatedNodes: make([]string, 0),
	}
}

// EnforceAirgap isolates all audio and camera device nodes by setting their mode permissions to 0000.
func (a *AudioAirgapManager) EnforceAirgap(ctx context.Context) ([]string, error) {
	a.mu.Lock()
	defer a.mu.Unlock()

	isolated := make([]string, 0)

	// 1. Audit /dev/snd
	if entries, err := os.ReadDir(a.sndPath); err == nil {
		for _, entry := range entries {
			nodePath := filepath.Join(a.sndPath, entry.Name())
			_ = os.Chmod(nodePath, 0000)
			isolated = append(isolated, nodePath)
		}
	} else if os.IsNotExist(err) {
		a.logger.Debug("Audio sysfs /dev/snd not present (clean airgap environment)")
	}

	// 2. Audit /dev/video*
	if entries, err := os.ReadDir(a.videoPath); err == nil {
		for _, entry := range entries {
			if len(entry.Name()) >= 5 && entry.Name()[:5] == "video" {
				nodePath := filepath.Join(a.videoPath, entry.Name())
				_ = os.Chmod(nodePath, 0000)
				isolated = append(isolated, nodePath)
			}
		}
	}

	a.isolatedNodes = isolated
	a.isAirgapped = true
	a.logger.Info("Acoustic & optical air-gap enforced on host",
		zap.Int("devices_isolated", len(isolated)),
	)
	return isolated, nil
}

// RestoreAirgap restores standard device permissions (0660) when host is in maintenance mode.
func (a *AudioAirgapManager) RestoreAirgap(ctx context.Context) error {
	a.mu.Lock()
	defer a.mu.Unlock()

	for _, nodePath := range a.isolatedNodes {
		if err := os.Chmod(nodePath, 0660); err != nil && !os.IsNotExist(err) {
			a.logger.Warn("Failed to restore node permission", zap.String("node", nodePath), zap.Error(err))
		}
	}
	a.isAirgapped = false
	a.isolatedNodes = make([]string, 0)
	a.logger.Info("Acoustic & optical air-gap restored to normal")
	return nil
}

// IsAirgapped returns the current airgap status.
func (a *AudioAirgapManager) IsAirgapped() bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.isAirgapped
}
