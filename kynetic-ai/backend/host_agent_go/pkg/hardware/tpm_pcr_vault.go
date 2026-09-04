package hardware

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sync"
)

// PCRSealedRootfsKey represents a container rootfs key sealed against TPM PCRs.
type PCRSealedRootfsKey struct {
	ContainerID     string `json:"container_id"`
	RequiredPCR0    string `json:"required_pcr0"`
	RequiredPCR1    string `json:"required_pcr1"`
	RequiredPCR7    string `json:"required_pcr7"`
	SealedCipherKey string `json:"sealed_cipher_key"`
}

// TPMPCRVault binds container rootfs decryption keys to immutable host platform PCR measurements.
type TPMPCRVault struct {
	mu         sync.Mutex
	vaultKeys  map[string]*PCRSealedRootfsKey
	masterSalt []byte
}

// NewTPMPCRVault instantiates a new TPM PCR rootfs vault.
func NewTPMPCRVault(masterSalt []byte) *TPMPCRVault {
	return &TPMPCRVault{
		vaultKeys:  make(map[string]*PCRSealedRootfsKey),
		masterSalt: masterSalt,
	}
}

// SealRootfsKey binds an AES-256 rootfs decryption key to host PCR0, PCR1, and PCR7 values.
func (t *TPMPCRVault) SealRootfsKey(containerID string, rawKey []byte, pcr0, pcr1, pcr7 string) *PCRSealedRootfsKey {
	t.mu.Lock()
	defer t.mu.Unlock()

	pcrComposite := fmt.Sprintf("%s:%s:%s", pcr0, pcr1, pcr7)
	h := hmac.New(sha256.New, t.masterSalt)
	h.Write([]byte(pcrComposite))
	kdfKey := h.Sum(nil)

	// Encrypt key with KDF derived key
	sealed := make([]byte, len(rawKey))
	for i := range rawKey {
		sealed[i] = rawKey[i] ^ kdfKey[i%len(kdfKey)]
	}

	record := &PCRSealedRootfsKey{
		ContainerID:     containerID,
		RequiredPCR0:    pcr0,
		RequiredPCR1:    pcr1,
		RequiredPCR7:    pcr7,
		SealedCipherKey: hex.EncodeToString(sealed),
	}

	t.vaultKeys[containerID] = record
	return record
}

// UnsealRootfsKey unseals the rootfs key only if current host PCR state matches exact expected values.
func (t *TPMPCRVault) UnsealRootfsKey(containerID, currentPCR0, currentPCR1, currentPCR7 string) ([]byte, error) {
	t.mu.Lock()
	defer t.mu.Unlock()

	record, exists := t.vaultKeys[containerID]
	if !exists {
		return nil, fmt.Errorf("no sealed key found for container %s", containerID)
	}

	if record.RequiredPCR0 != currentPCR0 || record.RequiredPCR1 != currentPCR1 || record.RequiredPCR7 != currentPCR7 {
		return nil, fmt.Errorf("TPM_PCR_ATTESTATION_MISMATCH: platform state has diverged, refusing rootfs unseal")
	}

	pcrComposite := fmt.Sprintf("%s:%s:%s", currentPCR0, currentPCR1, currentPCR7)
	h := hmac.New(sha256.New, t.masterSalt)
	h.Write([]byte(pcrComposite))
	kdfKey := h.Sum(nil)

	sealedBytes, err := hex.DecodeString(record.SealedCipherKey)
	if err != nil {
		return nil, fmt.Errorf("invalid sealed key format: %w", err)
	}

	unsealed := make([]byte, len(sealedBytes))
	for i := range sealedBytes {
		unsealed[i] = sealedBytes[i] ^ kdfKey[i%len(kdfKey)]
	}

	return unsealed, nil
}
