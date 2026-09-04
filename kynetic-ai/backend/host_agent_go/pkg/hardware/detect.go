// Package hardware detects physical hardware specs of the host machine.
//
// Replaces: backend/host_agent/hardware_detect.py
//
// Improvements over Python implementation:
//   - No pynvml/GPUtil Python packages required
//   - Reads NVML directly via cgo binding in pkg/benchmark/cuda_nvml.go
//   - Uses /sys/block and /proc natively without psutil
//   - Compiles into the static binary with zero runtime deps
package hardware

import (
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
)

// GPUInfo holds per-GPU hardware information.
type GPUInfo struct {
	Model         string
	VRAMgb        float64
	DriverVersion string
	CUDAVersion   string
	TemperatureC  *float64
	PowerDrawW    *float64
	UtilizationPct *float64
}

// GPUTelemetry represents live streaming metric samples from the GPU
type GPUTelemetry struct {
	Index          int     `json:"index"`
	Model          string  `json:"model"`
	TemperatureC   float64 `json:"temperature_c"`
	HotspotTempC   float64 `json:"hotspot_temp_c,omitempty"`
	PowerDrawW     float64 `json:"power_draw_w"`
	UtilizationPct float64 `json:"utilization_pct"`
	VRAMUsedMB     uint64  `json:"vram_used_mb"`
	VRAMTotalMB    uint64  `json:"vram_total_mb"`
}

// HardwareManifest holds the full hardware snapshot of the host.
// Matches backend HostRegistrationRequest.hardware JSON schema.
type HardwareManifest struct {
	CPUModel   string
	CPUCores   int
	CPUThreads int
	RAMgb      float64
	DiskGB     float64
	DiskType   string // "nvme" | "ssd" | "hdd" | "unknown"
	GPUs       []GPUInfo
	OSType     string // "linux" | "macos" | "windows"
}

// CollectManifest gathers a full hardware manifest from the local machine.
func CollectManifest() (*HardwareManifest, error) {
	osType := map[string]string{
		"linux":   "linux",
		"darwin":  "macos",
		"windows": "windows",
	}[runtime.GOOS]
	if osType == "" {
		osType = "linux"
	}

	cpuModel, cpuCores, cpuThreads := detectCPU()
	ramGB := detectRAM()
	diskGB, diskType := detectDisk()
	gpus := detectGPUs()

	return &HardwareManifest{
		CPUModel:   cpuModel,
		CPUCores:   cpuCores,
		CPUThreads: cpuThreads,
		RAMgb:      ramGB,
		DiskGB:     diskGB,
		DiskType:   diskType,
		GPUs:       gpus,
		OSType:     osType,
	}, nil
}

// ToAPIDict converts the manifest into the JSON structure expected by the backend API.
func (m *HardwareManifest) ToAPIDict() map[string]interface{} {
	d := map[string]interface{}{
		"cpu_model":   m.CPUModel,
		"cpu_cores":   m.CPUCores,
		"cpu_threads": m.CPUThreads,
		"ram_gb":      round2(m.RAMgb),
		"disk_gb":     round2(m.DiskGB),
		"disk_type":   m.DiskType,
		"gpu_count":   len(m.GPUs),
		"os_type":     m.OSType,
	}
	if len(m.GPUs) > 0 {
		g := m.GPUs[0]
		d["gpu_model"] = g.Model
		d["gpu_vram_gb"] = round2(g.VRAMgb)
		d["driver_version"] = g.DriverVersion
		d["cuda_version"] = g.CUDAVersion
		if g.TemperatureC != nil {
			d["temperature_c"] = *g.TemperatureC
		}
		if g.PowerDrawW != nil {
			d["power_draw_w"] = *g.PowerDrawW
		}
	}
	return d
}

func detectCPU() (model string, cores, threads int) {
	// Read /proc/cpuinfo on Linux
	if data, err := os.ReadFile("/proc/cpuinfo"); err == nil {
		lines := strings.Split(string(data), "\n")
		cpuSet := map[int]bool{}
		coreSet := map[string]bool{}
		for _, line := range lines {
			if strings.HasPrefix(line, "model name") {
				if model == "" {
					parts := strings.SplitN(line, ":", 2)
					if len(parts) == 2 {
						model = strings.TrimSpace(parts[1])
					}
				}
			}
			if strings.HasPrefix(line, "processor") {
				parts := strings.SplitN(line, ":", 2)
				if len(parts) == 2 {
					if id, err := strconv.Atoi(strings.TrimSpace(parts[1])); err == nil {
						cpuSet[id] = true
					}
				}
			}
			if strings.HasPrefix(line, "core id") {
				parts := strings.SplitN(line, ":", 2)
				if len(parts) == 2 {
					coreSet[strings.TrimSpace(parts[1])] = true
				}
			}
		}
		threads = len(cpuSet)
		cores = len(coreSet)
		if cores == 0 {
			cores = threads
		}
	}
	if model == "" {
		// macOS fallback
		out, err := exec.Command("sysctl", "-n", "machdep.cpu.brand_string").Output()
		if err == nil {
			model = strings.TrimSpace(string(out))
		}
	}
	if model == "" {
		model = fmt.Sprintf("%s/%s", runtime.GOOS, runtime.GOARCH)
	}
	if threads == 0 {
		threads = runtime.NumCPU()
		cores = threads
	}
	return
}

func detectRAM() float64 {
	if data, err := os.ReadFile("/proc/meminfo"); err == nil {
		for _, line := range strings.Split(string(data), "\n") {
			if strings.HasPrefix(line, "MemTotal:") {
				fields := strings.Fields(line)
				if len(fields) >= 2 {
					if kb, err := strconv.ParseFloat(fields[1], 64); err == nil {
						return kb / (1024 * 1024) // kB → GB
					}
				}
			}
		}
	}
	// macOS fallback
	if out, err := exec.Command("sysctl", "-n", "hw.memsize").Output(); err == nil {
		if bytes, err := strconv.ParseFloat(strings.TrimSpace(string(out)), 64); err == nil {
			return bytes / (1024 * 1024 * 1024)
		}
	}
	return 0
}

func detectDisk() (float64, string) {
	// Use df to get root filesystem total
	out, err := exec.Command("df", "-B1", "/").Output()
	totalGB := 0.0
	if err == nil {
		lines := strings.Split(string(out), "\n")
		if len(lines) >= 2 {
			fields := strings.Fields(lines[1])
			if len(fields) >= 2 {
				if b, err := strconv.ParseFloat(fields[1], 64); err == nil {
					totalGB = b / (1024 * 1024 * 1024)
				}
			}
		}
	}

	diskType := "unknown"
	// Check /sys/block for rotational flag
	entries, _ := os.ReadDir("/sys/block")
	for _, e := range entries {
		name := e.Name()
		if strings.HasPrefix(name, "sd") || strings.HasPrefix(name, "nvme") || strings.HasPrefix(name, "vd") {
			rotPath := fmt.Sprintf("/sys/block/%s/queue/rotational", name)
			if data, err := os.ReadFile(rotPath); err == nil {
				if strings.TrimSpace(string(data)) == "0" {
					if strings.HasPrefix(name, "nvme") {
						diskType = "nvme"
					} else {
						diskType = "ssd"
					}
				} else {
					diskType = "hdd"
				}
			}
			break
		}
	}
	return totalGB, diskType
}

// detectGPUs uses the NVML cgo binding from pkg/benchmark.
// Falls back to empty slice on non-NVIDIA or non-Linux hosts.
func detectGPUs() []GPUInfo {
	// GPU detection is delegated to cuda_nvml.go cgo binding
	// which is compiled only when CGO_ENABLED=1 on Linux with NVML installed.
	// On macOS dev builds this returns empty.
	return detectNVMLGPUs()
}

func round2(v float64) float64 {
	return float64(int(v*100)) / 100
}
