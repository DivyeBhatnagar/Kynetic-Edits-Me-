package firewall_test

import (
	"testing"

	"github.com/kynetic-ai/host-agent/pkg/firewall"
)

func TestLANAirGapManager(t *testing.T) {
	mgr := firewall.NewLANAirGapManager("inst-test-12345678")
	if mgr == nil || mgr.TableName == "" {
		t.Fatal("expected valid LANAirGapManager with TableName")
	}

	// Applying rules should handle environments without nft gracefully
	_ = mgr.ApplyAirGapRules("tap0")
	_ = mgr.TeardownAirGapRules()
}

func TestNetNSManager(t *testing.T) {
	mgr := firewall.NewNetNSManager("inst-test-12345678")
	if mgr == nil || mgr.NamespaceName == "" {
		t.Fatal("expected valid NetNSManager")
	}

	_ = mgr.CreateNamespace()
	_ = mgr.DeleteNamespace()
}
