# Kynetic CLI (`kynetic-cli`)

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Typer / Click](https://img.shields.io/badge/CLI-Click%20%2F%20Rich-green.svg)](https://click.palletsprojects.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

`kynetic` is the primary interface for Kynetic AI — a 100% Python executable built using `Click`, `Rich`, `httpx`, `websockets`, `Pydantic V2`, and `keyring`.

The CLI provides a fast, unmediated experience for discovering, launching, connecting to, transferring files to, and managing cloud compute instances directly from your terminal.

---

## ⚡ Installation

### Install in Editable Mode
```bash
cd cli
pip install -e .
```

Verify installation:
```bash
kynetic version
```

---

## 💻 Command Surface Reference

### Authentication
- **`kynetic login`**: Initiates the OAuth2 Device Authorization Grant flow. Prints a verification URL and user code, polls the auth gateway, and securely stores JWT access tokens in the system keychain (`keyring`).
- **`kynetic logout`**: Clears stored credential tokens from the OS keyring and `~/.kynetic/credentials`.
- **`kynetic config`**: Displays current CLI configuration parameters (API Gateway URL, default region, output formatting).

### Instance Lifecycle Management
- **`kynetic search`**: Queries available GPU and CPU compute listings with optional filters (`--gpu`, `--vram`, `--max-price`, `--region`).
- **`kynetic launch`**: Schedules and launches compute instance. Supports scheduler hint flags:
  - `--budget`: Prioritizes lower hourly price (50% price weighted).
  - `--fastest`: Prioritizes higher FP32 TFLOPS & benchmark performance (50% benchmark weighted).
  - Default: `--balanced` (6-factor weighted ranking).
- **`kynetic ls`**: Lists all active and historical compute instances for the authenticated developer.
- **`kynetic status <instance_id>`**: Shows live status, runtime duration, billed seconds, and host hardware specs for an instance.
- **`kynetic logs <instance_id>`**: Fetches and streams container execution logs.
- **`kynetic stop <instance_id>`**: Pauses a running instance.
- **`kynetic terminate <instance_id>`**: Terminates an instance, triggers DoD 3-pass storage shredding on the host, releases wallet holds, and verifies the cryptographic `SecureDeletionReceipt`.

### Developer Tooling & Connection Layer
- **`kynetic connect <instance_id>`**: Opens an instant, raw PTY terminal session (`termios`/`tty` raw mode) over reverse-dial WebSocket tunnel. Survives transient Wi-Fi drops with silent auto-reconnect.
- **`kynetic cp <src> <dst>`**: Resumable chunked file transfer in 1MB blocks with SHA-256 integrity checksum verification. Supports local-to-remote (`./data.tar.gz inst-123:/workspace/`) and remote-to-local transfers.
- **`kynetic ssh <instance_id>`**: Automatically generates and injects a `Host kynetic-<instance_id>` block into `~/.ssh/config`, enabling 1-click VS Code Remote SSH connections.
- **`kynetic tunnel`**: Creates local (`kynetic tunnel --local 8080 --remote 8080 <instance_id>`) or public (`kynetic tunnel --public --remote 8080 <instance_id>`) port forwarding tunnels.

---

## 🏗️ Internal Architecture

```
cli/kynetic_cli/
├── cli.py               # Main Click CLI command entry point & formatting
├── auth_client.py       # OAuth2 Device Authorization Grant client
├── instance_client.py   # Instance CRUD & lifecycle API client
├── connection.py       # WebSocket PTY terminal session client (raw mode)
├── file_transfer.py     # 1MB chunked resumable file transfer engine (SHA-256)
└── tunnel_manager.py    # Port forwarding & ~/.ssh/config entry generator
```

---

## 🧪 Testing the CLI

Run CLI unit and integration tests:
```bash
pytest cli/tests/test_cli_auth.py backend/tests/test_v6_phase_e_f_gateway_cli.py backend/tests/test_v6_phase_g_h_dx_scheduler.py
```
