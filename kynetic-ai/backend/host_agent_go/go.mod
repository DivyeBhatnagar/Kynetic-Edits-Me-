module github.com/kynetic-ai/host-agent

go 1.22

require (
	// containerd native Go SDK — replaces Python ctr CLI subprocess calls
	github.com/containerd/containerd/v2 v2.0.0
	// Firecracker native Go SDK — replaces Python firecracker.py subprocess driver
	github.com/firecracker-microvm/firecracker-go-sdk v1.0.0
	// nftables native netlink — replaces Python subprocess nft calls
	github.com/google/nftables v0.2.0
	// Structured logging — equivalent to Python structlog
	go.uber.org/zap v1.27.0
	// gRPC for mTLS control channel to Python provisioning service
	google.golang.org/grpc v1.67.0
	google.golang.org/protobuf v1.35.1
	// HTTP client for heartbeat and registration
	golang.org/x/net v0.29.0
)
