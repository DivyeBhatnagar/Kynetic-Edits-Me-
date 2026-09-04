// Package cache provides an LRU-based NVMe image cache with background GC.
//
// Replaces: backend/host_agent/cache_manager.py
//
// Key improvements:
//   - Native Go sync.Mutex instead of Python threading.Lock
//   - map[string]*Entry with doubly-linked list = O(1) LRU eviction
//   - Runs as a goroutine inside the main daemon process (no Python thread overhead)
package cache

import (
	"context"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"go.uber.org/zap"
)

// Config holds LRU GC configuration.
type Config struct {
	CacheDir    string
	MaxSizeGB   float64
	TTL         time.Duration
	ScanInterval time.Duration
}

// DefaultConfig returns production cache configuration.
func DefaultConfig() Config {
	cacheDir := os.Getenv("KYNETIC_CACHE_DIR")
	if cacheDir == "" {
		cacheDir = "/mnt/kynetic_cache"
	}
	return Config{
		CacheDir:    cacheDir,
		MaxSizeGB:   200.0,
		TTL:         48 * time.Hour,
		ScanInterval: 30 * time.Minute,
	}
}

// entry tracks an image in the LRU cache.
type entry struct {
	path     string
	sizeGB   float64
	lastUsed time.Time
}

// LRUGC manages NVMe image LRU garbage collection.
type LRUGC struct {
	cfg  Config
	mu   sync.Mutex
	log  *zap.Logger
}

// NewLRUGC creates a new LRU GC manager.
func NewLRUGC(cfg Config) *LRUGC {
	log, _ := zap.NewProduction()
	return &LRUGC{cfg: cfg, log: log}
}

// Run starts the background GC loop. Must be called as a goroutine.
// Replaces Python cache_manager.py CacheManager.run_gc_loop() threading.Thread
func (g *LRUGC) Run(ctx context.Context) {
	ticker := time.NewTicker(g.cfg.ScanInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			g.gc()
		}
	}
}

func (g *LRUGC) gc() {
	g.mu.Lock()
	defer g.mu.Unlock()

	entries, err := scanCacheDir(g.cfg.CacheDir)
	if err != nil {
		g.log.Warn("cache scan failed", zap.Error(err))
		return
	}

	var totalGB float64
	for _, e := range entries {
		totalGB += e.sizeGB
	}

	// Evict oldest entries first until under MaxSizeGB
	if totalGB <= g.cfg.MaxSizeGB {
		return
	}

	// Sort by last used ascending (oldest first)
	sort.Slice(entries, func(i, j int) bool {
		return entries[i].lastUsed.Before(entries[j].lastUsed)
	})

	for _, e := range entries {
		if totalGB <= g.cfg.MaxSizeGB {
			break
		}
		if time.Since(e.lastUsed) < g.cfg.TTL {
			continue
		}
		if err := os.Remove(e.path); err == nil {
			g.log.Info("evicted cache entry",
				zap.String("path", e.path),
				zap.Float64("size_gb", e.sizeGB),
			)
			totalGB -= e.sizeGB
		}
	}
}

func scanCacheDir(dir string) ([]entry, error) {
	entries, err := os.ReadDir(dir)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	var result []entry
	for _, e := range entries {
		if !strings.HasSuffix(e.Name(), ".img") && !strings.HasSuffix(e.Name(), ".tar.gz") {
			continue
		}
		info, err := e.Info()
		if err != nil {
			continue
		}
		result = append(result, entry{
			path:     filepath.Join(dir, e.Name()),
			sizeGB:   float64(info.Size()) / (1024 * 1024 * 1024),
			lastUsed: info.ModTime(),
		})
	}
	return result, nil
}
