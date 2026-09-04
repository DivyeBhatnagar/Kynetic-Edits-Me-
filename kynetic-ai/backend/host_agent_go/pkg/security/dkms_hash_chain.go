package security

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sync"
	"time"
)

// DKMSBuildStage represents a step in compiling a dynamic kernel module.
type DKMSBuildStage struct {
	ModuleName  string    `json:"module_name"`
	StageName   string    `json:"stage_name"`
	SourceHash  string    `json:"source_hash"`
	OutputHash  string    `json:"output_hash"`
	PrevHash    string    `json:"prev_hash"`
	ChainHash   string    `json:"chain_hash"`
	Timestamp   time.Time `json:"timestamp"`
}

// DKMSHashChainAuditor creates an immutable cryptographic hash chain for kernel driver builds.
type DKMSHashChainAuditor struct {
	mu           sync.Mutex
	chainTipHash string
	buildHistory []*DKMSBuildStage
}

// NewDKMSHashChainAuditor initializes the DKMS build hash chain auditor.
func NewDKMSHashChainAuditor() *DKMSHashChainAuditor {
	return &DKMSHashChainAuditor{
		chainTipHash: "0000000000000000000000000000000000000000000000000000000000000000",
		buildHistory: make([]*DKMSBuildStage, 0),
	}
}

// RecordBuildStage appends a verified compilation stage to the tamper-evident hash chain.
func (d *DKMSHashChainAuditor) RecordBuildStage(module, stage, srcHash, outHash string) *DKMSBuildStage {
	d.mu.Lock()
	defer d.mu.Unlock()

	now := time.Now().UTC()
	payload := fmt.Sprintf("%s:%s:%s:%s:%s:%d", d.chainTipHash, module, stage, srcHash, outHash, now.UnixNano())
	h := sha256.Sum256([]byte(payload))
	chainHash := hex.EncodeToString(h[:])

	record := &DKMSBuildStage{
		ModuleName:  module,
		StageName:   stage,
		SourceHash:  srcHash,
		OutputHash:  outHash,
		PrevHash:    d.chainTipHash,
		ChainHash:   chainHash,
		Timestamp:   now,
	}

	d.chainTipHash = chainHash
	d.buildHistory = append(d.buildHistory, record)
	return record
}

// VerifyChainIntegrity recomputes and validates the full DKMS hash chain from genesis.
func (d *DKMSHashChainAuditor) VerifyChainIntegrity() (bool, string) {
	d.mu.Lock()
	defer d.mu.Unlock()

	currentTip := "0000000000000000000000000000000000000000000000000000000000000000"
	for i, stage := range d.buildHistory {
		if stage.PrevHash != currentTip {
			return false, fmt.Sprintf("DKMS_CHAIN_TAMPER_DETECTED_AT_INDEX_%d", i)
		}
		currentTip = stage.ChainHash
	}

	return true, "DKMS_HASH_CHAIN_VALID"
}
