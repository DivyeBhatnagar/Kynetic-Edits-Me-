// cuda_nvml_stub.go — build stub for non-NVML platforms (macOS / CGO_ENABLED=0)
//
//go:build !nvml

package benchmark

import "github.com/kynetic-ai/host-agent/pkg/hardware"

// detectNVMLGPUs returns empty on non-NVML builds.
func detectNVMLGPUs() []hardware.GPUInfo {
	return nil
}

// runNVMLBenchmarks returns stub results on non-NVML builds.
func runNVMLBenchmarks() ([]BenchmarkResult, error) {
	return stubResults()
}
