"""
Host Agent — Main entry point.

Implements the guided, non-CLI onboarding wizard:

1. Welcome screen (detect if already registered)
2. Auth token prompt (user copies from Kynetic dashboard)
3. Hardware detection (live progress display)
4. Backend registration + mTLS cert issuance
5. Benchmark suite execution (progress bar)
6. Success screen + heartbeat loop start

Packaged via PyInstaller into a single executable:
  Windows: kynetic-agent.exe
  Linux/macOS: kynetic-agent

Usage:
  kynetic-agent                    — Guided onboarding wizard
  kynetic-agent --headless TOKEN   — Non-interactive mode (for servers)
"""

import os
import sys
import time
from pathlib import Path

import structlog

from libs.common.logging import configure_logging
from host_agent.agent_client import AgentConfig, KyneticAgentClient
from host_agent.benchmark_runner import run_all_benchmarks
from host_agent.hardware_detect import collect_hardware_manifest

configure_logging(log_level=os.environ.get("KYNETIC_LOG_LEVEL", "INFO"))
logger = structlog.get_logger(__name__)

AGENT_VERSION = "0.1.0"
DEFAULT_BACKEND_URL = os.environ.get("KYNETIC_BACKEND_URL", "https://api.kynetic.ai")


# ---------------------------------------------------------------------------
# Terminal UI helpers
# ---------------------------------------------------------------------------
def _clear():
    os.system("cls" if sys.platform == "win32" else "clear")


def _print_banner():
    print("\n" + "═" * 60)
    print("  ██╗  ██╗██╗   ██╗███╗   ██╗███████╗████████╗██╗ ██████╗")
    print("  ██║ ██╔╝╚██╗ ██╔╝████╗  ██║██╔════╝╚══██╔══╝██║██╔════╝")
    print("  █████╔╝  ╚████╔╝ ██╔██╗ ██║█████╗     ██║   ██║██║     ")
    print("  ██╔═██╗   ╚██╔╝  ██║╚██╗██║██╔══╝     ██║   ██║██║     ")
    print("  ██║  ██╗   ██║   ██║ ╚████║███████╗   ██║   ██║╚██████╗")
    print("  ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═══╝╚══════╝   ╚═╝   ╚═╝ ╚═════╝")
    print(f"\n  Host Agent v{AGENT_VERSION}  •  kynetic.ai")
    print("═" * 60 + "\n")


def _step(n: int, title: str):
    print(f"\n  ── Step {n}: {title} ──")


def _ok(msg: str):
    print(f"  ✅ {msg}")


def _info(msg: str):
    print(f"  ℹ  {msg}")


def _warn(msg: str):
    print(f"  ⚠  {msg}")


def _err(msg: str):
    print(f"  ❌ {msg}")


def _spinner(msg: str, seconds: float = 0.1):
    """Minimal inline spinner for async-like visual feedback."""
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    end_time = time.time() + seconds
    i = 0
    while time.time() < end_time:
        print(f"\r  {frames[i % len(frames)]} {msg}", end="", flush=True)
        time.sleep(0.08)
        i += 1
    print(f"\r  ✅ {msg}" + " " * 20)


# ---------------------------------------------------------------------------
# Guided wizard
# ---------------------------------------------------------------------------
def run_wizard(backend_url: str = DEFAULT_BACKEND_URL) -> int:
    _clear()
    _print_banner()

    config = AgentConfig.load(backend_url=backend_url, agent_version=AGENT_VERSION)

    # ── Already registered? ───────────────────────────────────────────────────
    if config.is_registered and config.host_id:
        _info(f"This machine is already registered as host: {config.host_id}")
        _info("Starting heartbeat loop...")
        _start_running(config, token=None)
        return 0

    # ── Step 1: Auth token ────────────────────────────────────────────────────
    _step(1, "Authentication")
    print("\n  Get your auth token from: https://app.kynetic.ai/settings/token")
    print("  (It starts with 'eyJ...')\n")
    token = input("  Paste your auth token: ").strip()
    if not token:
        _err("No token provided. Exiting.")
        return 1

    # ── Step 2: Hardware detection ────────────────────────────────────────────
    _step(2, "Detecting Your Hardware")
    print()
    _spinner("Scanning CPU, RAM, and disk...", seconds=1.0)
    manifest = collect_hardware_manifest()

    print(f"\n  Detected:")
    print(f"    CPU  : {manifest.cpu_model} ({manifest.cpu_cores} cores / {manifest.cpu_threads} threads)")
    print(f"    RAM  : {manifest.ram_gb:.1f} GB")
    print(f"    Disk : {manifest.disk_gb:.0f} GB ({manifest.disk_type.upper()})")
    if manifest.gpus:
        for g in manifest.gpus:
            print(f"    GPU  : {g.model} ({g.vram_gb:.0f} GB VRAM)")
    else:
        print("    GPU  : None detected (CPU-only mode)")

    confirm = input("\n  Does this look correct? [Y/n] ").strip().lower()
    if confirm == "n":
        _warn("Hardware detection is automatic. If specs are wrong, try updating GPU drivers.")

    # ── Step 3: Register with backend ─────────────────────────────────────────
    _step(3, "Registering with Kynetic")
    print()
    _spinner("Connecting to Kynetic AI...", seconds=0.5)

    client = KyneticAgentClient(config=config, auth_token=token)
    success = client.register(manifest)

    if not success:
        _err("Registration failed. Check your auth token and internet connection.")
        return 1

    _ok(f"Registered! Host ID: {config.host_id}")

    # ── Step 4: Benchmark suite ───────────────────────────────────────────────
    _step(4, "Running Benchmark Suite")
    print("\n  This measures your hardware performance. It takes ~30–60 seconds.\n")
    print("  ┌─────────────────────────────────────┐")
    print("  │  Running LLM inference benchmark... │")
    results = run_all_benchmarks(duration_per_benchmark=10.0)
    print("  │  Running image-gen benchmark...      │")
    print("  │  Running FLOPs benchmark...          │")
    print("  └─────────────────────────────────────┘")

    submitted = client.submit_benchmarks(results)
    if not submitted:
        _warn("Benchmark submission failed. Will retry on next connection.")
    else:
        for r in results:
            print(f"    {r.benchmark_type:<20}: {r.score:.2f} {'tok/s' if r.benchmark_type == 'llm_inference' else ('steps/s' if r.benchmark_type == 'image_gen' else 'TFLOPS')}")

    # ── Step 5: Start heartbeat loop ──────────────────────────────────────────
    _step(5, "Going Live")
    print()
    _ok("Your host is verified and ready to earn!")
    _info("The agent will now run in the background, sending heartbeats to Kynetic.")
    _info(f"Logs: {Path.home() / '.kynetic_agent' / 'agent.log'}")
    print()

    _start_running(config, token=token)
    return 0


def _start_running(config: AgentConfig, token: str | None) -> None:
    """Start heartbeat and rebenchmark listener — runs until interrupted."""
    if token is None:
        # Load token from env on restart
        token = os.environ.get("KYNETIC_AUTH_TOKEN", "")

    client = KyneticAgentClient(config=config, auth_token=token)
    client.start_heartbeat_loop()
    client.listen_for_rebenchmark()

    print("  Agent is running. Press Ctrl+C to stop.\n")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        client.stop_heartbeat_loop()
        print("\n  Agent stopped.")


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------
def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        prog="kynetic-agent",
        description="Kynetic AI Host Agent — Share your compute, earn rewards.",
    )
    parser.add_argument(
        "--headless",
        metavar="TOKEN",
        help="Run without interactive wizard (for servers/CI). Provide auth token directly.",
    )
    parser.add_argument(
        "--backend-url",
        default=DEFAULT_BACKEND_URL,
        help="Kynetic backend URL (default: https://api.kynetic.ai)",
    )
    parser.add_argument("--version", action="version", version=f"kynetic-agent {AGENT_VERSION}")
    args = parser.parse_args()

    if args.headless:
        config = AgentConfig.load(backend_url=args.backend_url, agent_version=AGENT_VERSION)
        if not config.is_registered:
            manifest = collect_hardware_manifest()
            client = KyneticAgentClient(config=config, auth_token=args.headless)
            if not client.register(manifest):
                return 1
            results = run_all_benchmarks()
            client.submit_benchmarks(results)
        _start_running(config, token=args.headless)
        return 0

    return run_wizard(backend_url=args.backend_url)


if __name__ == "__main__":
    sys.exit(main())
