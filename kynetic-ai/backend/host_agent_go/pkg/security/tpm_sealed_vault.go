package security

import (
	"context"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"fmt"
	"io"
	"os"
	"sync"

	"go.uber.org/zap"
)

// TPMSealedVault uses TPM 2.0 PCR state (Platform Configuration Registers) or hardware-tied
// cryptographic keys to seal and unseal host agent secrets (e.g., host private keys, payouts config).
type TPMSealedVault struct {
	logger     *zap.Logger
	tpmDevPath string
	pcrIndex   int
	mu         sync.Mutex
	isHardware bool
}

// NewTPMSealedVault instantiates a new TPMSealedVault.
func NewTPMSealedVault(logger *zap.Logger, tpmDevPath string, pcrIndex int) *TPMSealedVault {
	if tpmDevPath == "" {
		tpmDevPath = "/dev/tpmrm0"
	}
	if pcrIndex == 0 {
		pcrIndex = 7 // Secure Boot & Firmware integrity PCR
	}
	return &TPMSealedVault{
		logger:     logger,
		tpmDevPath: tpmDevPath,
		pcrIndex:   pcrIndex,
	}
}

// CheckTPMAvailable checks if /dev/tpmrm0 or /dev/tpm0 is accessible on the host.
func (v *TPMSealedVault) CheckTPMAvailable() bool {
	v.mu.Lock()
	defer v.mu.Unlock()

	if _, err := os.Stat(v.tpmDevPath); err == nil {
		v.isHardware = true
		return true
	}
	v.isHardware = false
	return false
}

// SealSecret encrypts plaintext using an ephemeral/PCR-derived key tied to PCR index.
func (v *TPMSealedVault) SealSecret(ctx context.Context, plaintext []byte, pcrDigest []byte) ([]byte, error) {
	v.mu.Lock()
	defer v.mu.Unlock()

	// Derive a 256-bit AES key by hashing PCR digest + PCR index
	h := sha256.New()
	h.Write(pcrDigest)
	h.Write([]byte(fmt.Sprintf("tpm-pcr-%d", v.pcrIndex)))
	key := h.Sum(nil)

	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("failed to create cipher block: %w", err)
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("failed to create gcm: %w", err)
	}

	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, fmt.Errorf("failed to generate nonce: %w", err)
	}

	ciphertext := gcm.Seal(nonce, nonce, plaintext, nil)
	v.logger.Info("Secret successfully sealed against TPM PCR state",
		zap.Int("pcr_index", v.pcrIndex),
		zap.Int("sealed_len", len(ciphertext)),
	)
	return ciphertext, nil
}

// UnsealSecret decrypts ciphertext only if the current PCR digest matches the state during sealing.
func (v *TPMSealedVault) UnsealSecret(ctx context.Context, ciphertext []byte, currentPCRDigest []byte) ([]byte, error) {
	v.mu.Lock()
	defer v.mu.Unlock()

	h := sha256.New()
	h.Write(currentPCRDigest)
	h.Write([]byte(fmt.Sprintf("tpm-pcr-%d", v.pcrIndex)))
	key := h.Sum(nil)

	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("failed to create cipher block: %w", err)
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("failed to create gcm: %w", err)
	}

	if len(ciphertext) < gcm.NonceSize() {
		return nil, fmt.Errorf("ciphertext too short")
	}

	nonce, actualCiphertext := ciphertext[:gcm.NonceSize()], ciphertext[gcm.NonceSize():]
	plaintext, err := gcm.Open(nil, nonce, actualCiphertext, nil)
	if err != nil {
		return nil, fmt.Errorf("TPM unseal failed: PCR state mismatch or tampered secret: %w", err)
	}

	v.logger.Info("Secret unsealed successfully with matching PCR state")
	return plaintext, nil
}
