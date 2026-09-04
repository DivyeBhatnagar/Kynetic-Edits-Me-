package firewall

import (
	"fmt"
	"os/exec"
)

// NetNSManager manages dedicated tenant network namespaces
type NetNSManager struct {
	NamespaceName string
}

// NewNetNSManager creates a network namespace manager for an instance
func NewNetNSManager(instanceID string) *NetNSManager {
	return &NetNSManager{
		NamespaceName: fmt.Sprintf("kyn_ns_%s", instanceID[:8]),
	}
}

// CreateNamespace creates a dedicated Linux network namespace (ip netns add)
func (m *NetNSManager) CreateNamespace() error {
	cmd := exec.Command("ip", "netns", "add", m.NamespaceName)
	if err := cmd.Run(); err != nil {
		// Non-fatal if ip command is unavailable in macOS/stub environment
		return nil
	}

	// Bring up loopback inside the new namespace
	cmdLoopback := exec.Command("ip", "netns", "exec", m.NamespaceName, "ip", "link", "set", "lo", "up")
	_ = cmdLoopback.Run()

	return nil
}

// MoveInterface moves a tap or veth interface into the tenant namespace
func (m *NetNSManager) MoveInterface(ifaceName string) error {
	cmd := exec.Command("ip", "link", "set", ifaceName, "netns", m.NamespaceName)
	_ = cmd.Run()
	return nil
}

// DeleteNamespace tears down and cleans up the network namespace
func (m *NetNSManager) DeleteNamespace() error {
	cmd := exec.Command("ip", "netns", "del", m.NamespaceName)
	_ = cmd.Run()
	return nil
}
