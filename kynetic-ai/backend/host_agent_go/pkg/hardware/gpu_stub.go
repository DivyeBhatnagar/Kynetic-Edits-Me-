// gpu_stub.go — hardware stub for non-NVML builds
//
//go:build !nvml

package hardware

// detectNVMLGPUs returns empty on non-NVIDIA builds.
// Implemented by pkg/benchmark on nvml-tagged builds.
func detectNVMLGPUs() []GPUInfo { return nil }
