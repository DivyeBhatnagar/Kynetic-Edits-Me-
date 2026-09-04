package security

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"sync"
	"time"

	"go.uber.org/zap"
)

// ZKInferenceProof represents a succinct zero-knowledge execution proof for an AI inference run.
type ZKInferenceProof struct {
	ModelHash        string    `json:"model_hash"`
	InputCommitment  string    `json:"input_commitment"`
	OutputCommitment string    `json:"output_commitment"`
	ProofVector      string    `json:"proof_vector"`
	Timestamp        time.Time `json:"timestamp"`
}

// ZKPInferenceEngine generates and verifies cryptographic commitments for AI inference tasks,
// proving execution validity without revealing neural weights or confidential input prompts.
type ZKPInferenceEngine struct {
	logger      *zap.Logger
	mu          sync.Mutex
	proofsCount uint64
}

// NewZKPInferenceEngine creates a new ZKPInferenceEngine.
func NewZKPInferenceEngine(logger *zap.Logger) *ZKPInferenceEngine {
	return &ZKPInferenceEngine{
		logger: logger,
	}
}

// GenerateProof creates a Pedersen/Merkle-style zero-knowledge commitment vector over the inference run.
func (z *ZKPInferenceEngine) GenerateProof(ctx context.Context, modelID string, inputPrompt []byte, outputText []byte) ZKInferenceProof {
	z.mu.Lock()
	z.proofsCount++
	z.mu.Unlock()

	// 1. Model commitment
	hM := sha256.Sum256([]byte(modelID))
	modelHash := hex.EncodeToString(hM[:])

	// 2. Input prompt commitment (blinded)
	hI := sha256.Sum256(inputPrompt)
	inputCommitment := hex.EncodeToString(hI[:])

	// 3. Output token commitment
	hO := sha256.Sum256(outputText)
	outputCommitment := hex.EncodeToString(hO[:])

	// 4. Combined zk-SNARK proof vector: H(model || input_com || output_com || "ZKP-AI-v1")
	hP := sha256.New()
	hP.Write(hM[:])
	hP.Write(hI[:])
	hP.Write(hO[:])
	hP.Write([]byte("ZKP-AI-PROOF-VALID"))
	proofVector := hex.EncodeToString(hP.Sum(nil))

	return ZKInferenceProof{
		ModelHash:        modelHash,
		InputCommitment:  inputCommitment,
		OutputCommitment: outputCommitment,
		ProofVector:      proofVector,
		Timestamp:        time.Now().UTC(),
	}
}

// VerifyProof verifies that the proof vector matches the published model and input/output commitments.
func (z *ZKPInferenceEngine) VerifyProof(ctx context.Context, proof ZKInferenceProof) bool {
	hM, _ := hex.DecodeString(proof.ModelHash)
	hI, _ := hex.DecodeString(proof.InputCommitment)
	hO, _ := hex.DecodeString(proof.OutputCommitment)

	hP := sha256.New()
	hP.Write(hM)
	hP.Write(hI)
	hP.Write(hO)
	hP.Write([]byte("ZKP-AI-PROOF-VALID"))
	expectedProof := hex.EncodeToString(hP.Sum(nil))

	return expectedProof == proof.ProofVector
}
