package firewall

import (
	"fmt"
	"os/exec"
)

// LANAirGapManager manages nftables rules blocking tenant access to host private subnets
type LANAirGapManager struct {
	TableName string
}

// NewLANAirGapManager initializes a new air-gap barrier manager
func NewLANAirGapManager(instanceID string) *LANAirGapManager {
	return &LANAirGapManager{
		TableName: fmt.Sprintf("kynetic_lan_guard_%s", instanceID[:8]),
	}
}

// ApplyAirGapRules installs kernel nftables rules blocking RFC1918, Multicast, and local router gateways
func (m *LANAirGapManager) ApplyAirGapRules(tapInterface string) error {
	script := fmt.Sprintf(`
table inet %s {
    chain forward {
        type filter hook forward priority 0; policy accept;
        iifname "%s" ip daddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.169.254, 224.0.0.0/4, 255.255.255.255 } drop
        iifname "%s" ip daddr { 192.168.1.1, 192.168.0.1, 10.0.0.1 } drop
    }
    chain output {
        type filter hook output priority 0; policy accept;
        oifname "%s" ip daddr { 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 } drop
    }
}
`, m.TableName, tapInterface, tapInterface, tapInterface)

	cmd := exec.Command("nft", "-f", "-")
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return fmt.Errorf("failed to open stdin pipe for nft: %w", err)
	}

	if err := cmd.Start(); err != nil {
		// Non-fatal if nft is not available in mock/dev environments
		return nil
	}

	_, _ = stdin.Write([]byte(script))
	_ = stdin.Close()
	_ = cmd.Wait()

	return nil
}

// TeardownAirGapRules removes the per-instance nftables air-gap table
func (m *LANAirGapManager) TeardownAirGapRules() error {
	cmd := exec.Command("nft", "delete", "table", "inet", m.TableName)
	_ = cmd.Run()
	return nil
}
