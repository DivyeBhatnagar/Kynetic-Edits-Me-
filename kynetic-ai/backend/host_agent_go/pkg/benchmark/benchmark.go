// Package benchmark provides CUDA/NVML GPU benchmarking via cgo bindings.
//
// Replaces: backend/host_agent/benchmark_runner.py
//
// On Linux hosts with NVIDIA GPU + NVML installed:
//   Build with: CGO_ENABLED=1 go build -tags nvml ./...
//
// On macOS / CI / non-NVIDIA hosts:
//   Build with: CGO_ENABLED=0 go build ./...   (NVML stubs return empty results)
package benchmark

import "fmt"

// BenchmarkResult mirrors the Python BenchmarkResult dataclass.
type BenchmarkResult struct {
	BenchmarkType string  // "cuda_gemm_fp16" | "cuda_gemm_fp32" | "nvml_vram"
	Score         float64 // TFLOPS for GEMM, GB for VRAM
	Units         string
	GPUIndex      int
	Passed        bool
}

// RunAll runs the full benchmark suite across all detected GPUs.
// On non-NVIDIA hosts, returns stub results for development.
func RunAll() ([]BenchmarkResult, error) {
	return runNVMLBenchmarks()
}

// ToAPIDict converts a BenchmarkResult to the JSON shape expected by the backend.
func (r BenchmarkResult) ToAPIDict() map[string]interface{} {
	return map[string]interface{}{
		"benchmark_type": r.BenchmarkType,
		"score":          r.Score,
		"units":          r.Units,
		"gpu_index":      r.GPUIndex,
		"passed":         r.Passed,
	}
}

// Stub for non-NVML builds — returns informational results.
func stubResults() ([]BenchmarkResult, error) {
	fmt.Println("[benchmark] NVML not available — running stub benchmarks (dev mode)")
	return []BenchmarkResult{
		{
			BenchmarkType: "stub_cpu_score",
			Score:         100.0,
			Units:         "arbitrary",
			GPUIndex:      0,
			Passed:        true,
		},
	}, nil
}
