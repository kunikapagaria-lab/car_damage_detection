"""WebSocket endpoint for live dashboard feed of inspection results.

Broadcasts each InspectionResult to all connected clients as JSON.
Pings clients every 30 seconds and removes unresponsive connections.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Thread-safe manager for active WebSocket connections."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        logger.info("ws_client_connected", total=len(self._connections))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)
        logger.info("ws_client_disconnected", total=len(self._connections))

    async def broadcast(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, default=str)
        dead: list[WebSocket] = []
        async with self._lock:
            targets = list(self._connections)
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)
            logger.warning("ws_dead_connections_removed", count=len(dead))

    async def ping_all(self) -> None:
        """Ping every client; remove those that don't respond within 5 seconds."""
        async with self._lock:
            targets = list(self._connections)
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                pong = await asyncio.wait_for(ws.send_text(json.dumps({"event": "ping"})), timeout=5.0)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)
            logger.warning("ws_ping_removed_dead", count=len(dead))

    @property
    def connection_count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


@router.websocket("/ws/live-feed")
async def live_feed(ws: WebSocket) -> None:
    await manager.connect(ws)
    mode = os.environ.get("PREDICTOR_MODE", "dummy")
    try:
        await ws.send_text(json.dumps({
            "event": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
        }))
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=35.0)
                logger.debug("ws_message_received", data=data)
            except asyncio.TimeoutError:
                try:
                    await ws.send_text(json.dumps({"event": "ping"}))
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)


async def _ping_loop() -> None:
    """Background task: ping all clients every 30 seconds."""
    while True:
        await asyncio.sleep(30)
        await manager.ping_all()


async def _queue_processor_loop(frame_queue: asyncio.Queue) -> None:
    """Background task: read CameraFrames, run full pipeline, broadcast results."""
    import functools
    from inference.lpr import detect_plate
    from inference.predictor_factory import get_predictor

    loop = asyncio.get_event_loop()

    while True:
        try:
            camera_frame = await frame_queue.get()
            predictor = get_predictor()

            plate_result, damages = await asyncio.gather(
                loop.run_in_executor(
                    None, functools.partial(detect_plate, camera_frame.frame_np)
                ),
                loop.run_in_executor(
                    None, functools.partial(predictor.predict, camera_frame.frame_np)
                ),
            )

            payload: dict[str, Any] = {
                "event": "inspection_result",
                "camera_id": camera_frame.camera_id,
                "angle": camera_frame.angle,
                "captured_at": camera_frame.captured_at.isoformat()
                if camera_frame.captured_at
                else None,
                "frame_hash": camera_frame.frame_hash,
                "plate": {
                    "plate_text": plate_result.plate_text,
                    "confidence": plate_result.confidence,
                    "bbox": plate_result.bbox,
                } if plate_result else None,
                "damages": [
                    {
                        "annotation_id": d.annotation_id,
                        "class_name": d.class_name,
                        "confidence": d.confidence,
                        "bbox_xyxy": d.bbox_xyxy,
                        "mask_area_pct": d.mask_area_pct,
                    }
                    for d in damages
                ],
                "n_damages": len(damages),
            }

            await manager.broadcast(payload)
            logger.info(
                "ws_broadcast_sent",
                camera_id=camera_frame.camera_id,
                n_damages=len(damages),
                n_clients=manager.connection_count,
            )
            frame_queue.task_done()

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("queue_processor_error", error=str(exc))
