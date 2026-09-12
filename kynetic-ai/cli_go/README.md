# Kynetic CLI (Go Production Binary)

[![Go Version](https://img.shields.io/badge/Go-1.22%2B-00ADD8.svg)](https://go.dev/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Startup Time](https://img.shields.io/badge/Startup-~2ms-brightgreen.svg)]()
[![Binary Size](https://img.shields.io/badge/Size-~8MB-blue.svg)]()

The **Kynetic Go CLI** (`kynetic`) is the official, high-performance production command-line client for Kynetic AI. It is compiled to a single, zero-dependency static binary delivering instant (~2ms) startup times, native PTY raw terminal streaming, and seamless microVM compute orchestration.

---

## ⚡ Performance Comparison: Go vs Python CLI

| Metric | Python CLI (`cli/`) | Go CLI (`cli_go/`) | Improvement |
|---|---|---|---|
| **Startup Latency** | ~800 ms | **~2 ms** | **400× faster** |
| **Binary / Bundle Size** | ~55 MB (wheel + env) | **~8 MB (single binary)** | **87% smaller** |
| **PTY First-Byte Latency** | ~18 ms | **~2 ms** | **9× lower** |
| **Dependencies** | Python 3.10+, pip, venv | **Zero external dependencies** | **Static distribution** |
| **Shell Experience** | termios / select loop | Native `golang.org/x/term` raw mode | True terminal emulation |

---

## 📦 Installation & Build

### 1. Build from Source
Ensure Go 1.22+ is installed:

```bash
cd cli_go
go build -ldflags="-s -w" -o kynetic .
```

### 2. Install to System Path
```bash
# macOS / Linux:
sudo mv kynetic /usr/local/bin/
kynetic version

# Windows (PowerShell as Administrator):
# Compile directly:
go build -o kynetic.exe .
# Add to User PATH or move to C:\Windows\System32
.\kynetic.exe version
```

### 3. Cross-Compilation for Distribution

Compile standalone binaries for all supported developer platforms:

```bash
# Linux (x86_64)
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o dist/kynetic-linux-amd64 .

# Linux (ARM64)
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build -ldflags="-s -w" -o dist/kynetic-linux-arm64 .

# macOS (Apple Silicon M1/M2/M3/M4)
CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build -ldflags="-s -w" -o dist/kynetic-darwin-arm64 .

# macOS (Intel)
CGO_ENABLED=0 GOOS=darwin GOARCH=amd64 go build -ldflags="-s -w" -o dist/kynetic-darwin-amd64 .

# Windows (x86_64)
CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -ldflags="-s -w" -o dist/kynetic-windows-amd64.exe .
```

---

## 💻 Command Surface Reference

### 🔐 Authentication (`kynetic login`, `kynetic logout`)
- **`kynetic login`**: Initiates the OAuth2 Device Authorization Grant flow. Automatically opens or prints the device verification URL and polls until the token is granted. Stored at `~/.kynetic/config.json`.
- **`kynetic logout`**: Clears saved credentials and active JWT tokens.

```bash
kynetic login
kynetic logout
```

### 🚀 Compute Launch Wizard (`kynetic launch`)
Orchestrates marketplace search (`GET /v1/search/listings`), automated 6-factor scheduler selection, instance provisioning (`POST /v1/instances`), and immediate PTY terminal connection in one command:

```bash
# Interactive launch with GPU selection
kynetic launch --gpu "RTX 4090"

# Non-interactive launch (ideal for CI/CD and scripts)
kynetic launch --gpu "A100" --region "us-east" --max-price 2.50 --yes

# Resume connection to an existing instance
kynetic launch --resume inst-984e72a1
```

**Supported Flags**:
- `--gpu <model>`: GPU model filter (e.g. `RTX 4090`, `A100`, `H100`, `L40S`).
- `--region <region>`: Geographic region filter (e.g. `us-east`, `eu-west`, `ap-south`).
- `--max-price <price>`: Maximum hourly rate in USD ($).
- `--hours <hours>`: Desired compute reservation duration (default: `1.0`).
- `--yes`, `-y`: Non-interactive auto-confirmation of the top-ranked compute node.
- `--resume <id>`: Reconnect directly to a previously provisioned instance.

### 🔌 PTY Terminal Connect (`kynetic connect`)
Spawns a raw-mode PTY terminal session with full ANSI color, window resize propagation (`SIGWINCH`), and automatic session reconnect over the reverse-dial WebSocket / SSH gateway:

```bash
kynetic connect inst-984e72a1
```

### 🖥️ Instance Management (`kynetic instances`)
Full lifecycle inspection and teardown of active and past compute microVMs:

```bash
# List all active & terminated instances
kynetic instances ls

# Inspect real-time hardware status, CPU/GPU telemetry, and accumulated cost
kynetic instances status inst-984e72a1

# Stream instance container stdout/stderr logs
kynetic instances logs inst-984e72a1

# Pause a running instance
kynetic instances stop inst-984e72a1

# Terminate instance, release billing holds, and trigger DoD storage shredding
kynetic instances terminate inst-984e72a1
```

### 💳 Dual-Currency Wallet (`kynetic wallet`)
Inspect developer balance and ledger history directly from the terminal:

```bash
# Show current USD ($) and INR (₹) balances
kynetic wallet balance

# List recent billing transactions, holds, and usage debits
kynetic wallet transactions
```

---

## ⚙️ Configuration (`~/.kynetic/config.json`)

The Go CLI automatically initializes and reads from `~/.kynetic/config.json`:

```json
{
  "api_url": "https://api.kynetic.ai",
  "auth_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "default_region": "us-east"
}
```

You can override the API URL at runtime using the `--api-url` global flag or `KYNETIC_API_URL` environment variable:

```bash
kynetic --api-url http://localhost:8000 instances ls
```

---

## 🏗️ Codebase Layout

```
cli_go/
├── cmd/
│   ├── root.go        # Cobra root command, global flags, and config persistence
│   ├── auth.go        # OAuth2 device authorization grant & token lifecycle
│   ├── launch.go      # Smart search ranking, 1-click launch flow & resume
│   ├── connect.go     # Raw terminal PTY session over reverse-dial gateway
│   ├── instances.go   # Instance CRUD (ls, status, logs, stop, terminate)
│   └── wallet.go      # Balance query and ledger transaction log viewer
├── go.mod             # Go module definition (github.com/divyebhatnagar/kynetic/cli_go)
├── go.sum             # Cryptographic dependency checksums
└── main.go            # Application entrypoint
```

---

## 🤝 Relationship with Python CLI (`cli/`)

- `cli_go/` is the **production binary** distributed to end users.
- `cli/` is retained as a reference/prototype Python package for test harnesses and backwards compatibility.
