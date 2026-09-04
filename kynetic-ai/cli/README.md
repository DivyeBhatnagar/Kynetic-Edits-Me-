# Kynetic CLI (Python Reference Implementation)

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Typer / Click](https://img.shields.io/badge/CLI-Click%20%2F%20Rich-green.svg)](https://click.palletsprojects.com/)
[![Status](https://img.shields.io/badge/Status-Reference%20%2F%20Test%20Harness-yellow.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> [!NOTE]
> **Production Migration Notice (v7.0.0)**:
> The official production binary for Kynetic developers is the **Go CLI** located at [`cli_go/`](../cli_go/).
> The Go CLI starts in **~2ms** (400× faster) and is distributed as a single ~8MB static binary.
> This Python CLI implementation is maintained as a reference and for executing integration test suites (`cli/tests/`).

---

## ⚡ Python CLI Installation (Development & Testing)

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
- **`kynetic launch`**: Single-command terminal workflow orchestrating search (`GET /v1/search/listings`) ➔ selection ➔ instance provisioning (`POST /v1/instances`) ➔ auto-connection PTY shell without opening a browser. Supports:
  - `--gpu <model>`: Filter by GPU model (e.g. `RTX 4090`, `A100`).
  - `--region <region>`: Filter by geographic region.
  - `--max-price <price>`: Maximum hourly price ($USD).
  - `--hours <hours>`: Initial hold duration requested.
  - `--yes` / `-y`: Auto-confirm top-ranked listing without interactive prompts.
  - `--resume <instance_id>`: Resume connection to an already provisioned instance ID without duplicate provisioning.
- **`kynetic ls`**: Lists all active and historical compute instances for the authenticated developer.
- **`kynetic status <instance_id>`**: Shows live status, runtime duration, billed seconds, and host hardware specs for an instance.
- **`kynetic logs <instance_id>`**: Fetches and streams container execution logs.
- **`kynetic stop <instance_id>`**: Pauses a running instance.
- **`kynetic terminate <instance_id>`**: Terminates an instance, triggers DoD storage shredding on the host, releases billing holds, and verifies the cryptographic `SecureDeletionReceipt`.

### Developer Tooling & Connection Layer
- **`kynetic connect <instance_id>`**: Opens a raw PTY terminal session (`termios`/`tty` raw mode) over reverse-dial WebSocket tunnel.
- **`kynetic cp <src> <dst>`**: Resumable chunked file transfer in 1MB blocks with SHA-256 integrity checksum verification.
- **`kynetic ssh <instance_id>`**: Automatically generates and injects a `Host kynetic-<instance_id>` block into `~/.ssh/config`, enabling 1-click VS Code Remote SSH connections.
- **`kynetic tunnel`**: Creates local (`kynetic tunnel --local 8080 --remote 8080 <instance_id>`) or public (`kynetic tunnel --public --remote 8080 <instance_id>`) port forwarding tunnels.

---

## 🏗️ Internal Architecture

```
cli/kynetic_cli/
├── cli.py               # Main Click CLI command entry point & launch wizard
├── auth_client.py       # OAuth2 Device Authorization Grant client
├── instance_client.py   # Instance CRUD & lifecycle API client
├── connection.py        # WebSocket PTY terminal session client (raw mode)
├── file_transfer.py     # 1MB chunked resumable file transfer engine (SHA-256)
└── tunnel_manager.py    # Port forwarding & ~/.ssh/config entry generator
```

---

## 🧪 Testing the CLI

Run CLI unit and integration tests:
```bash
pytest cli/tests/test_cli_auth.py backend/tests/test_v6_phase_e_f_gateway_cli.py backend/tests/test_v6_phase_g_h_dx_scheduler.py backend/tests/test_v8_feature_4_5_6_search_launch.py
```
