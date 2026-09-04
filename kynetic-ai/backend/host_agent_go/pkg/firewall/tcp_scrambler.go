package firewall

import (
	"crypto/rand"
	"encoding/binary"
	"sync"
	"time"

	"go.uber.org/zap"
)

// ScrambledTCPHeader represents sanitized TCP connection parameters.
type ScrambledTCPHeader struct {
	InitialSequenceNum uint32    `json:"initial_sequence_num"`
	TimestampOffset    uint32    `json:"timestamp_offset"`
	ScrambledAt        time.Time `json:"scrambled_at"`
}

// TCPScrambler randomizes TCP Initial Sequence Numbers (ISNs) and timestamps
// to defeat remote OS fingerprinting (Nmap/ZMap OS detection) and TCP hijack attacks.
type TCPScrambler struct {
	logger          *zap.Logger
	mu              sync.Mutex
	scrambledPacks  uint64
}

// NewTCPScrambler creates a new TCPScrambler.
func NewTCPScrambler(logger *zap.Logger) *TCPScrambler {
	return &TCPScrambler{
		logger: logger,
	}
}

// ScrambleTCPParams generates unpredictable cryptographic ISN and timestamp offsets.
func (t *TCPScrambler) ScrambleTCPParams() ScrambledTCPHeader {
	t.mu.Lock()
	t.scrambledPacks++
	t.mu.Unlock()

	b := make([]byte, 8)
	_, _ = rand.Read(b)

	isn := binary.BigEndian.Uint32(b[:4])
	tsOffset := binary.BigEndian.Uint32(b[4:])

	return ScrambledTCPHeader{
		InitialSequenceNum: isn,
		TimestampOffset:    tsOffset,
		ScrambledAt:        time.Now().UTC(),
	}
}

// GetScrambledCount returns count of scrambled TCP sessions.
func (t *TCPScrambler) GetScrambledCount() uint64 {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.scrambledPacks
}
