package hardware

import (
	"context"
	"math/rand"
	"sync"
	"time"

	"go.uber.org/zap"
)

// GEMMNoiseInjector injects microsecond jitter and slight frequency dithering into
// GPU compute loops to prevent neural network layer reconstruction via side-channel analysis.
type GEMMNoiseInjector struct {
	logger       *zap.Logger
	jitterRangeUs int
	mu           sync.Mutex
	totalPings   uint64
}

// NewGEMMNoiseInjector creates a new GEMMNoiseInjector.
func NewGEMMNoiseInjector(logger *zap.Logger, jitterRangeUs int) *GEMMNoiseInjector {
	if jitterRangeUs <= 0 {
		jitterRangeUs = 50 // 50 microseconds max jitter
	}
	return &GEMMNoiseInjector{
		logger:        logger,
		jitterRangeUs: jitterRangeUs,
	}
}

// ApplyJitterDelay sleeps for a randomized microsecond interval to obscure precise kernel timing.
func (g *GEMMNoiseInjector) ApplyJitterDelay(ctx context.Context) time.Duration {
	g.mu.Lock()
	g.totalPings++
	g.mu.Unlock()

	jitter := time.Duration(rand.Intn(g.jitterRangeUs)+1) * time.Microsecond
	time.Sleep(jitter)
	return jitter
}

// GetTotalInjections returns total jitter delays applied.
func (g *GEMMNoiseInjector) GetTotalInjections() uint64 {
	g.mu.Lock()
	defer g.mu.Unlock()
	return g.totalPings
}
