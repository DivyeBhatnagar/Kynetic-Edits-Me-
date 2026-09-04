package security

import (
	"testing"
	"time"
)

func TestSpeculativeFenceDesync(t *testing.T) {
	desync := NewSpeculativeFenceDesync(100 * time.Millisecond)

	desync.EmitExecutionSerializationFence()
	err := desync.DesynchronizeBranchPredictor()
	if err != nil {
		t.Fatalf("branch predictor desynchronization failed: %v", err)
	}

	st := desync.Status()
	if !st.LFenceSerialized || !st.BPUScrubbed {
		t.Fatalf("expected active fence serialization & BPU scrubbing")
	}
	if st.FencesEmitted < 2 {
		t.Fatalf("expected at least 2 fences emitted, got %d", st.FencesEmitted)
	}
}
