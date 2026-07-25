"""
Gateway Service — Session Manager (session_manager.py)

Tracks active Host Agent reverse-dial WebSocket connections and developer PTY spliced sessions.
"""

import asyncio
from typing import Dict, Optional
import structlog
from fastapi import WebSocket

log = structlog.get_logger(__name__)


class GatewaySessionManager:
    """
    In-memory registry for active host tunnels and active PTY sessions.
    (In production, session routing hints are backed by Redis).
    """

    def __init__(self):
        # host_id -> WebSocket connection from host agent
        self._host_tunnels: Dict[str, WebSocket] = {}
        # instance_id -> dict of active PTY sessions
        self._pty_sessions: Dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def register_host_tunnel(self, host_id: str, websocket: WebSocket) -> None:
        """Register persistent reverse-dial WebSocket from host agent."""
        async with self._lock:
            self._host_tunnels[str(host_id)] = websocket
            log.info("gateway.host_tunnel_registered", host_id=str(host_id))

    async def unregister_host_tunnel(self, host_id: str) -> None:
        """Unregister host tunnel when connection drops."""
        async with self._lock:
            self._host_tunnels.pop(str(host_id), None)
            log.info("gateway.host_tunnel_unregistered", host_id=str(host_id))

    def get_host_tunnel(self, host_id: str) -> Optional[WebSocket]:
        """Fetch active host tunnel WebSocket."""
        return self._host_tunnels.get(str(host_id))

    def is_host_connected(self, host_id: str) -> bool:
        """Check if host agent is currently connected to Gateway."""
        return str(host_id) in self._host_tunnels


gateway_sessions = GatewaySessionManager()
