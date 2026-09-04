module github.com/kynetic-ai/host-agent

go 1.22.0

require (
	// containerd native Go SDK — replaces Python ctr CLI subprocess calls
	github.com/containerd/containerd/v2 v2.0.0
	// Firecracker native Go SDK — replaces Python firecracker.py subprocess driver
	github.com/firecracker-microvm/firecracker-go-sdk v1.0.0
	// nftables native netlink — replaces Python subprocess nft calls
	github.com/google/nftables v0.2.0
	// Structured logging — equivalent to Python structlog
	go.uber.org/zap v1.28.0
	// HTTP client for heartbeat and registration
	golang.org/x/net v0.30.0
	// gRPC for mTLS control channel to Python provisioning service
	google.golang.org/grpc v1.67.1
	google.golang.org/protobuf v1.35.1
)

require go.uber.org/multierr v1.10.0 // indirect
