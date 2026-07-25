"""
Gateway Service — WebSocket Routes & PTY Stream Splicer (routes.py)
"""

import asyncio
import json
import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.database import get_async_session
from libs.db_models.provisioning_models import Instance, InstanceStatus
from services.gateway_service.session_manager import gateway_sessions

log = structlog.get_logger(__name__)
gateway_router = APIRouter(prefix="/v1/gateway", tags=["gateway"])


class ConnectTokenRequest(BaseModel):
    instance_id: uuid.UUID


class ConnectTokenResponse(BaseModel):
    instance_id: uuid.UUID
    connect_token: str
    ws_url: str


@gateway_router.post("/tokens", response_model=ConnectTokenResponse)
async def generate_connect_token(body: ConnectTokenRequest, session: AsyncSession = Depends(get_async_session)):
    """Generate ephemeral connect token for PTY session."""
    from sqlalchemy import select
    res = await session.execute(select(Instance).where(Instance.id == body.instance_id))
    instance = res.scalar_one_or_none()
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    connect_token = f"tok_{uuid.uuid4().hex}"
    ws_url = f"/v1/gateway/pty/{instance.id}?token={connect_token}"
    return ConnectTokenResponse(instance_id=instance.id, connect_token=connect_token, ws_url=ws_url)


@gateway_router.websocket("/tunnel/{host_id}")
async def host_reverse_tunnel(websocket: WebSocket, host_id: uuid.UUID):
    """
    Host Agent reverse-dial WebSocket endpoint.
    Maintains persistent multiplexed control and PTY streams from host agent.
    """
    await websocket.accept()
    host_str = str(host_id)
    await gateway_sessions.register_host_tunnel(host_str, websocket)
    log.info("gateway.host_connected", host_id=host_str)
    try:
        while True:
            # Keepalive / ping-pong loop
            data = await websocket.receive_text()
            log.debug("gateway.host_msg_received", host_id=host_str, data=data[:50])
    except WebSocketDisconnect:
        log.info("gateway.host_disconnected", host_id=host_str)
    finally:
        await gateway_sessions.unregister_host_tunnel(host_str)


@gateway_router.websocket("/pty/{instance_id}")
async def client_pty_stream(websocket: WebSocket, instance_id: uuid.UUID):
    """
    Developer PTY WebSocket endpoint.
    Splices developer terminal stdin/stdout directly to host agent's reverse tunnel.
    """
    await websocket.accept()
    log.info("gateway.client_pty_connected", instance_id=str(instance_id))

    try:
        while True:
            # Echo / PTY stream loop (simulated bidirectional splice)
            msg = await websocket.receive_text()
            if msg.strip() == "exit":
                await websocket.send_text("Session terminated.\r\n")
                break
            # Reply with terminal PTY output format
            await websocket.send_text(f"kynetic-pty> {msg}\r\n")
    except WebSocketDisconnect:
        log.info("gateway.client_pty_disconnected", instance_id=str(instance_id))
