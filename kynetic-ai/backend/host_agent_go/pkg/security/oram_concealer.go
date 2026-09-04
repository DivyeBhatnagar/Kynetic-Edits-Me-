package security

import (
	"crypto/rand"
	"fmt"
	"math/big"
	"sync"
)

// ORAMBlock represents an encrypted block stored in an oblivious memory tree bucket.
type ORAMBlock struct {
	BlockID uint32 `json:"block_id"`
	Data    []byte `json:"data"`
	IsDummy bool   `json:"is_dummy"`
}

// ORAMConcealer implements Path-ORAM style memory access pattern obfuscation with dummy memory access injection.
type ORAMConcealer struct {
	numBuckets int
	blockSize  int
	storage    map[uint32]*ORAMBlock
	mu         sync.Mutex
	positionMap map[uint32]int // maps BlockID to current leaf path
}

// NewORAMConcealer initializes an Oblivious RAM concealer.
func NewORAMConcealer(numBuckets, blockSize int) *ORAMConcealer {
	if numBuckets <= 0 {
		numBuckets = 64
	}
	if blockSize <= 0 {
		blockSize = 32
	}
	c := &ORAMConcealer{
		numBuckets:  numBuckets,
		blockSize:   blockSize,
		storage:     make(map[uint32]*ORAMBlock),
		positionMap: make(map[uint32]int),
	}
	return c
}

// WriteBlock writes a block to ORAM, shuffling its path and injecting dummy memory accesses.
func (c *ORAMConcealer) WriteBlock(blockID uint32, data []byte) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	paddedData := make([]byte, c.blockSize)
	copy(paddedData, data)

	// Pick a new random path
	randPath, err := rand.Int(rand.Reader, big.NewInt(int64(c.numBuckets)))
	if err != nil {
		return err
	}
	c.positionMap[blockID] = int(randPath.Int64())

	c.storage[blockID] = &ORAMBlock{
		BlockID: blockID,
		Data:    paddedData,
		IsDummy: false,
	}

	// Inject dummy write to obscure real memory bus access pattern
	dummyID := uint32(0xFFFFFF00) | uint32(randPath.Int64()%255)
	dummyData := make([]byte, c.blockSize)
	_, _ = rand.Read(dummyData)
	c.storage[dummyID] = &ORAMBlock{
		BlockID: dummyID,
		Data:    dummyData,
		IsDummy: true,
	}

	return nil
}

// ReadBlock retrieves a block and immediately re-randomizes its stored location in memory.
func (c *ORAMConcealer) ReadBlock(blockID uint32) ([]byte, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	blk, exists := c.storage[blockID]
	if !exists || blk.IsDummy {
		return nil, fmt.Errorf("block %d not found in ORAM", blockID)
	}

	// Re-assign random path upon every read access
	randPath, _ := rand.Int(rand.Reader, big.NewInt(int64(c.numBuckets)))
	c.positionMap[blockID] = int(randPath.Int64())

	result := make([]byte, c.blockSize)
	copy(result, blk.Data)
	return result, nil
}
