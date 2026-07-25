"""
Host Agent — Backend Communication Client.

Handles all communication between the Host Agent and the Kynetic AI backend:
- Registration (POST /hosts/register)
- Benchmark submission (POST /hosts/{host_id}/benchmarks)
- Heartbeat loop (POST /hosts/heartbeat every N seconds)
- Rebenchmark command subscription (Redis pub/sub)

mTLS is implemented via the client cert/key issued at registration:
stored in the agent config directory and used for all subsequent requests.
"""

import json
import os
import threading
import time
import uuid
from pathlib import Path

import httpx
import structlog

from host_agent.benchmark_runner import run_all_benchmarks
from host_agent.hardware_detect import HardwareManifest, collect_hardware_manifest

logger = structlog.get_logger(__name__)

# Agent config directory — persists host_id, cert, and key between restarts
AGENT_CONFIG_DIR = Path(os.environ.get("KYNETIC_AGENT_DIR", Path.home() / ".kynetic_agent"))
CONFIG_FILE = AGENT_CONFIG_DIR / "config.json"
CERT_FILE = AGENT_CONFIG_DIR / "client.crt"
KEY_FILE = AGENT_CONFIG_DIR / "client.key"


class AgentConfig:
    """Persisted agent configuration (host_id, cert paths, backend URL)."""

    def __init__(self, backend_url: str, agent_version: str = "0.1.0") -> None:
        self.backend_url = backend_url
        self.agent_version = agent_version
        self.agent_id: str = str(uuid.uuid4())  # Generated once, persisted
        self.host_id: str | None = None
        self.is_registered: bool = False

    def save(self) -> None:
        AGENT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump({
                "backend_url": self.backend_url,
                "agent_version": self.agent_version,
                "agent_id": self.agent_id,
                "host_id": self.host_id,
                "is_registered": self.is_registered,
            }, f, indent=2)

    @classmethod
    def load(cls, backend_url: str, agent_version: str = "0.1.0") -> "AgentConfig":
        config = cls(backend_url, agent_version)
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                data = json.load(f)
            config.agent_id = data.get("agent_id", config.agent_id)
            config.host_id = data.get("host_id")
            config.is_registered = data.get("is_registered", False)
        return config


def _build_client(cert_auth: tuple | None = None) -> httpx.Client:
    """
    Build an httpx.Client with optional mTLS client cert.
    cert_auth = (cert_path, key_path) for mTLS.
    """
    kwargs: dict = {"timeout": httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=5.0)}
    if cert_auth and all(Path(p).exists() for p in cert_auth):
        kwargs["cert"] = cert_auth
    return httpx.Client(**kwargs)


class KyneticAgentClient:
    """
    HTTP client for communicating with the Kynetic AI backend.

    After registration, all requests use the mTLS client cert
    for Security Pillar 1 compliance.
    """

    HEARTBEAT_INTERVAL_SECONDS = 30

    def __init__(self, config: AgentConfig, auth_token: str) -> None:
        self.config = config
        self.auth_token = auth_token
        self._heartbeat_thread: threading.Thread | None = None
        self._stop_heartbeat = threading.Event()

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
        }

    def _get_client(self) -> httpx.Client:
        if CERT_FILE.exists() and KEY_FILE.exists():
            return _build_client(cert_auth=(str(CERT_FILE), str(KEY_FILE)))
        return _build_client()

    # ── Registration ─────────────────────────────────────────────────────────
    def register(self, manifest: HardwareManifest) -> bool:
        """
        Register this host with the backend.
        On success: saves host_id, writes mTLS cert, updates config.
        Returns True if registration succeeded (even if spec was flagged).
        """
        payload = {
            "agent_id": self.config.agent_id,
            "agent_version": self.config.agent_version,
            "os_type": manifest.os_type,
            "hardware": manifest.to_api_dict(),
        }

        with _build_client() as client:
            try:
                resp = client.post(
                    f"{self.config.backend_url}/hosts/register",
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                self.config.host_id = str(data["host_id"])
                self.config.is_registered = True

                # Store the mTLS cert returned by the server
                AGENT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                CERT_FILE.write_text(data["mtls_client_cert_pem"])
                CERT_FILE.chmod(0o600)

                self.config.save()
                logger.info(
                    "host_registered",
                    host_id=self.config.host_id,
                    status=data.get("status"),
                )
                return True
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "registration_failed",
                    status_code=exc.response.status_code,
                    detail=exc.response.text[:500],
                )
                return False
            except Exception as exc:
                logger.error("registration_error", error=str(exc))
                return False

    # ── Benchmark submission ──────────────────────────────────────────────────
    def submit_benchmarks(self, results: list) -> bool:
        """Submit benchmark results to the backend."""
        if not self.config.host_id:
            logger.error("submit_benchmarks_no_host_id")
            return False

        payload = {
            "host_id": self.config.host_id,
            "results": [r.to_api_dict() for r in results],
        }

        with self._get_client() as client:
            try:
                resp = client.post(
                    f"{self.config.backend_url}/hosts/{self.config.host_id}/benchmarks",
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                logger.info(
                    "benchmarks_submitted",
                    host_id=self.config.host_id,
                    all_passed=data.get("all_passed"),
                    new_status=data.get("host_status"),
                )
                return True
            except Exception as exc:
                logger.error("benchmark_submission_failed", error=str(exc))
                return False

    # ── Heartbeat ─────────────────────────────────────────────────────────────
    def send_heartbeat(self, status: str = "idle") -> None:
        """Send a single heartbeat to the backend."""
        if not self.config.host_id:
            return

        # Collect live telemetry for this heartbeat
        import psutil
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            temp = float(pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU))
            power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0
            util = float(pynvml.nvmlDeviceGetUtilizationRates(handle).gpu)
            pynvml.nvmlShutdown()
        except Exception:
            temp = power = util = None

        ram = psutil.virtual_memory()
        ram_used = round(ram.used / (1024 ** 3), 2)

        payload = {
            "host_id": self.config.host_id,
            "status": status,
            "temperature_c": temp,
            "power_draw_w": power,
            "gpu_utilization_pct": util,
            "ram_used_gb": ram_used,
        }

        with self._get_client() as client:
            try:
                resp = client.post(
                    f"{self.config.backend_url}/hosts/heartbeat",
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                logger.debug("heartbeat_sent", status=status)
            except Exception as exc:
                logger.warning("heartbeat_failed", error=str(exc))

    def start_heartbeat_loop(self, interval_seconds: int = HEARTBEAT_INTERVAL_SECONDS) -> None:
        """Start the background heartbeat thread."""
        self._stop_heartbeat.clear()

        def _loop():
            while not self._stop_heartbeat.is_set():
                self.send_heartbeat()
                self._stop_heartbeat.wait(timeout=interval_seconds)

        self._heartbeat_thread = threading.Thread(target=_loop, daemon=True, name="heartbeat")
        self._heartbeat_thread.start()
        logger.info("heartbeat_loop_started", interval_seconds=interval_seconds)

    def stop_heartbeat_loop(self) -> None:
        self._stop_heartbeat.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)

    # ── Rebenchmark command listener ──────────────────────────────────────────
    def listen_for_rebenchmark(self) -> None:
        """
        Subscribe to the Redis pub/sub channel for this host's commands.
        When a 'rebenchmark' command arrives, run benchmarks and submit.
        Runs in a background daemon thread.
        """
        if not self.config.host_id:
            return

        import redis
        channel = f"kynetic:host:{self.config.host_id}:commands"

        def _subscribe():
            try:
                r = redis.from_url(
                    os.environ.get("KYNETIC_REDIS_URL", "redis://localhost:6379/0")
                )
                pubsub = r.pubsub()
                pubsub.subscribe(channel)
                logger.info("rebenchmark_listener_started", channel=channel)

                for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    try:
                        cmd = json.loads(message["data"])
                        if cmd.get("command") == "rebenchmark":
                            logger.info("rebenchmark_command_received")
                            results = run_all_benchmarks()
                            self.submit_benchmarks(results)
                    except Exception as exc:
                        logger.error("rebenchmark_command_error", error=str(exc))
            except Exception as exc:
                logger.error("rebenchmark_listener_error", error=str(exc))

        t = threading.Thread(target=_subscribe, daemon=True, name="rebenchmark_listener")
        t.start()
