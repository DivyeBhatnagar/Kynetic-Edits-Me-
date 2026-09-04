package security

import (
	"crypto/rand"
	"fmt"
	"sync"
	"time"
)

// CanaryTrap represents an in-memory buffer barrier checking for out-of-bounds corruption
type CanaryTrap struct {
	ID        string    `json:"id"`
	CreatedAt time.Time `json:"created_at"`
	MagicWord [32]byte  `json:"magic_word"`
	Buffer    []byte    `json:"-"`
}

// OperatorKillSwitch provides physical machine owner emergency controls
type OperatorKillSwitch struct {
	mu           sync.Mutex
	IsTriggered  bool      `json:"is_triggered"`
	TriggeredAt  *time.Time `json:"triggered_at,omitempty"`
	Reason       string    `json:"reason,omitempty"`
	Canaries     []*CanaryTrap
}

// NewOperatorKillSwitch initializes emergency operator controls
func NewOperatorKillSwitch() *OperatorKillSwitch {
	return &OperatorKillSwitch{
		Canaries: make([]*CanaryTrap, 0),
	}
}

// PlantCanary creates a monitored canary memory block
func (k *OperatorKillSwitch) PlantCanary(canaryID string) (*CanaryTrap, error) {
	k.mu.Lock()
	defer k.mu.Unlock()

	var magic [32]byte
	if _, err := rand.Read(magic[:]); err != nil {
		return nil, fmt.Errorf("failed to generate canary magic word: %w", err)
	}

	buf := make([]byte, 4096)
	copy(buf[:32], magic[:])
	copy(buf[4096-32:], magic[:])

	canary := &CanaryTrap{
		ID:        canaryID,
		CreatedAt: time.Now().UTC(),
		MagicWord: magic,
		Buffer:    buf,
	}

	k.Canaries = append(k.Canaries, canary)
	return canary, nil
}

// VerifyCanaries checks all planted canaries for memory tampering
func (k *OperatorKillSwitch) VerifyCanaries() (bool, error) {
	k.mu.Lock()
	defer k.mu.Unlock()

	for _, c := range k.Canaries {
		// Verify header and footer match original magic word
		if string(c.Buffer[:32]) != string(c.MagicWord[:]) ||
			string(c.Buffer[4096-32:]) != string(c.MagicWord[:]) {
			now := time.Now().UTC()
			k.IsTriggered = true
			k.TriggeredAt = &now
			k.Reason = fmt.Sprintf("memory canary %s corrupted by unauthorized buffer overwrite", c.ID)
			return false, fmt.Errorf("SECURITY ALERT: %s", k.Reason)
		}
	}
	return true, nil
}

// EmergencyKill manually triggers immediate host shutdown of all active tenant instances
func (k *OperatorKillSwitch) EmergencyKill(operatorReason string) {
	k.mu.Lock()
	defer k.mu.Unlock()

	now := time.Now().UTC()
	k.IsTriggered = true
	k.TriggeredAt = &now
	k.Reason = fmt.Sprintf("physical operator manual kill triggered: %s", operatorReason)
}
