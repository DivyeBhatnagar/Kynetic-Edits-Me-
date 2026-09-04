package hardware

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// IOMMUDevice represents a PCI device within an IOMMU group
type IOMMUDevice struct {
	PCIAddress string `json:"pci_address"`
	VendorID   string `json:"vendor_id,omitempty"`
	DeviceID   string `json:"device_id,omitempty"`
	Class      string `json:"class,omitempty"`
}

// IOMMUGroup represents an isolated IOMMU memory group
type IOMMUGroup struct {
	GroupID int           `json:"group_id"`
	Devices []IOMMUDevice `json:"devices"`
}

// IOMMUGovStatus represents the overall IOMMU status of the system
type IOMMUGovStatus struct {
	IOMMUEnabled bool         `json:"iommu_enabled"`
	DriverType   string       `json:"driver_type"` // "intel_iommu", "amd_iommu", or "none"
	GPUGroups    []IOMMUGroup `json:"gpu_groups"`
	IsIsolated   bool         `json:"is_isolated"`
	Errors       []string     `json:"errors,omitempty"`
}

// CheckIOMMUGroups inspects the Linux sysfs IOMMU groups to verify hardware DMA isolation
func CheckIOMMUGroups() (*IOMMUGovStatus, error) {
	status := &IOMMUGovStatus{
		GPUGroups: make([]IOMMUGroup, 0),
		Errors:    make([]string, 0),
	}

	iommuBase := "/sys/kernel/iommu_groups"
	if _, err := os.Stat(iommuBase); os.IsNotExist(err) {
		status.IOMMUEnabled = false
		status.DriverType = "none"
		status.IsIsolated = false
		status.Errors = append(status.Errors, "IOMMU is disabled or not supported by host BIOS/kernel (intel_iommu=on or amd_iommu=on required)")
		return status, nil
	}

	status.IOMMUEnabled = true

	// Check kernel cmdline for driver type
	if cmdlineBytes, err := os.ReadFile("/proc/cmdline"); err == nil {
		cmdline := string(cmdlineBytes)
		if strings.Contains(cmdline, "intel_iommu=on") {
			status.DriverType = "intel_iommu"
		} else if strings.Contains(cmdline, "amd_iommu=on") {
			status.DriverType = "amd_iommu"
		} else {
			status.DriverType = "generic_iommu"
		}
	}

	// Traverse IOMMU groups
	groups, err := os.ReadDir(iommuBase)
	if err != nil {
		return status, fmt.Errorf("failed to read %s: %w", iommuBase, err)
	}

	for _, g := range groups {
		if !g.IsDir() {
			continue
		}
		devicesPath := filepath.Join(iommuBase, g.Name(), "devices")
		devices, err := os.ReadDir(devicesPath)
		if err != nil {
			continue
		}

		var groupDevices []IOMMUDevice
		hasGPU := false

		for _, d := range devices {
			pciAddr := d.Name()
			dev := IOMMUDevice{PCIAddress: pciAddr}

			// Read class code to identify GPU (0x0300 or 0x0302)
			classFile := filepath.Join("/sys/bus/pci/devices", pciAddr, "class")
			if classBytes, err := os.ReadFile(classFile); err == nil {
				dev.Class = strings.TrimSpace(string(classBytes))
				if strings.HasPrefix(dev.Class, "0x0300") || strings.HasPrefix(dev.Class, "0x0302") {
					hasGPU = true
				}
			}

			groupDevices = append(groupDevices, dev)
		}

		if hasGPU {
			var gid int
			fmt.Sscanf(g.Name(), "%d", &gid)
			iGroup := IOMMUGroup{
				GroupID: gid,
				Devices: groupDevices,
			}
			status.GPUGroups = append(status.GPUGroups, iGroup)

			// Check for unsafe shared devices (NVMe 0x0108, USB 0x0c03, Ethernet 0x0200)
			for _, d := range groupDevices {
				if strings.HasPrefix(d.Class, "0x0108") || strings.HasPrefix(d.Class, "0x0c03") {
					status.IsIsolated = false
					status.Errors = append(status.Errors, fmt.Sprintf("GPU in group %d shares IOMMU with non-GPU peripheral %s", gid, d.PCIAddress))
				}
			}
		}
	}

	if len(status.GPUGroups) > 0 && len(status.Errors) == 0 {
		status.IsIsolated = true
	}

	return status, nil
}
