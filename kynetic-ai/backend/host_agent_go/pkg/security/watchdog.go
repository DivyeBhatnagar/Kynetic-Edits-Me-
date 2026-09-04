package security

import (
	"context"
	"fmt"
	"os"
	"sync"
	"time"

	"go.uber.org/zap"
)

// HardwareWatchdog manages heartbeat pings to `/dev/watchdog` (or a simulated watchdog timer)
// to ensure the host PC automatically hard-resets if kernel hangs or fork bombs freeze the system.
type HardwareWatchdog struct {
	logger       *zap.Logger
	devicePath   string
	pingInterval time.Duration
	fileHandle   *os.File
	mu           sync.Mutex
	isRunning    bool
	stopChan     chan struct{}
}

// NewHardwareWatchdog constructs a new HardwareWatchdog.
func NewHardwareWatchdog(logger *zap.Logger, devicePath string, pingInterval time.Duration) *HardwareWatchdog {
	if devicePath == "" {
		devicePath = "/dev/watchdog"
	}
	if pingInterval == 0 {
		pingInterval = 10 * time.Second
	}
	return &HardwareWatchdog{
		logger:       logger,
		devicePath:   devicePath,
		pingInterval: pingInterval,
		stopChan:     make(chan struct{}),
	}
}

// ArmWatchdog opens the watchdog device and starts background ping heartbeats.
func (w *HardwareWatchdog) ArmWatchdog(ctx context.Context) error {
	w.mu.Lock()
	defer w.mu.Unlock()

	if w.isRunning {
		return nil
	}

	f, err := os.OpenFile(w.devicePath, os.O_WRONLY, 0)
	if err != nil {
		if os.IsNotExist(err) || os.IsPermission(err) {
			w.logger.Debug("Hardware watchdog device not accessible, running simulated watchdog daemon",
				zap.String("path", w.devicePath),
			)
		} else {
			return fmt.Errorf("failed to open watchdog device: %w", err)
		}
	}
	w.fileHandle = f
	w.isRunning = true
	w.stopChan = make(chan struct{})

	go w.pingLoop()
	w.logger.Info("Hardware Watchdog armed", zap.Duration("interval", w.pingInterval))
	return nil
}

// pingLoop sends regular keep-alive writes to the watchdog device.
func (w *HardwareWatchdog) pingLoop() {
	ticker := time.NewTicker(w.pingInterval)
	defer ticker.Stop()

	for {
		select {
		case <-w.stopChan:
			return
		case <-ticker.C:
			w.mu.Lock()
			if w.fileHandle != nil {
				_, _ = w.fileHandle.Write([]byte{0})
			}
			w.mu.Unlock()
		}
	}
}

// DisarmSafely stops the watchdog ping loop and sends the magic close char 'V' to /dev/watchdog if present.
func (w *HardwareWatchdog) DisarmSafely() error {
	w.mu.Lock()
	defer w.mu.Unlock()

	if !w.isRunning {
		return nil
	}

	close(w.stopChan)
	w.isRunning = false

	if w.fileHandle != nil {
		// Magic char 'V' tells the Linux watchdog driver to disable without resetting
		_, _ = w.fileHandle.Write([]byte("V"))
		_ = w.fileHandle.Close()
		w.fileHandle = nil
	}

	w.logger.Info("Hardware Watchdog disarmed cleanly")
	return nil
}

// IsArmed returns true if the watchdog is actively pinging.
func (w *HardwareWatchdog) IsArmed() bool {
	w.mu.Lock()
	defer w.mu.Unlock()
	return w.isRunning
}
