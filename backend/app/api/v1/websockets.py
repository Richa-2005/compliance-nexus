import json
import logging
from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("ComplianceNexus.WebSocket")

ws_router = APIRouter(tags=["WebSocket Stream"])


class ConnectionManager:

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            f"⚡ [WEBSOCKET CONNECTED]: Active clients: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(
                f"🔌 [WEBSOCKET DISCONNECTED]: Remaining clients: {len(self.active_connections)}"
            )

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Failed to broadcast to socket client: {e}")


manager = ConnectionManager()


@ws_router.websocket("/ws/live-feed")
async def websocket_live_feed(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # initial connection handshake frame
        await websocket.send_text(
            json.dumps(
                {
                    "event": "SYSTEM_CONNECTED",
                    "channel": "live_telemetry_feed",
                    "message": "Real-time compliance monitoring feed active.",
                }
            )
        )

        while True:
            # Keep socket alive and respond to client pings
            data = await websocket.receive_text()
            await websocket.send_text(
                json.dumps({"event": "PONG", "payload": data})
            )

    except WebSocketDisconnect:
        manager.disconnect(websocket)