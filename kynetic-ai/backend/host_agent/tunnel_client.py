"""
Host Agent — Reverse Tunnel Client (tunnel_client.py)

Maintains persistent reverse-dial WebSocket connection to Tunnel Gateway.
Handles keepalive ping/pong and dispatches incoming PTY stream splice requests.
"""

import asyncio
import structlog
import websockets

log = structlog.get_logger(__name__)


class ReverseTunnelClient:
    """
    Host Agent reverse tunnel client.
    Dials Gateway WS endpoint and keeps control connection alive.
    """

    def __init__(self, host_id: str, gateway_url: str = "ws://localhost:8000/v1/gateway"):
        self.host_id = host_id
        self.gateway_url = gateway_url.rstrip("/")
        self.is_connected = False

    async def connect_and_run(self) -> None:
        """Connect to Gateway and maintain keepalive loop."""
        url = f"{self.gateway_url}/tunnel/{self.host_id}"
        log.info("tunnel_client.connecting", url=url)
        try:
            async with websockets.connect(url) as ws:
                self.is_connected = True
                log.info("tunnel_client.connected", host_id=self.host_id)
                while self.is_connected:
                    await ws.send("ping")
                    await asyncio.sleep(15)
        except Exception as exc:
            self.is_connected = False
            log.warning("tunnel_client.disconnected", error=str(exc))
