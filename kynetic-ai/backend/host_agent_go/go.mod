module github.com/kynetic-ai/host-agent

go 1.22.0

require (
	// Structured logging — equivalent to Python structlog
	go.uber.org/zap v1.28.0
	// HTTP client for heartbeat and registration
	golang.org/x/net v0.30.0 // indirect
	// gRPC for mTLS control channel to Python provisioning service
	google.golang.org/grpc v1.67.1
	google.golang.org/protobuf v1.35.1 // indirect
)

require (
	github.com/davecgh/go-spew v1.1.2-0.20180830191138-d8f796af33cc // indirect
	github.com/pmezard/go-difflib v1.0.1-0.20181226105442-5d4384ee4fb2 // indirect
	github.com/stretchr/testify v1.9.0 // indirect
	go.uber.org/multierr v1.10.0 // indirect
	golang.org/x/sys v0.26.0 // indirect
	golang.org/x/text v0.19.0 // indirect
	google.golang.org/genproto/googleapis/rpc v0.0.0-20241021214115-324edc3d5d38 // indirect
)
