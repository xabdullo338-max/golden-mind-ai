from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .event_bus import EventBus

router = APIRouter()

def install_websocket_routes(app, event_bus: EventBus) -> None:
    @app.websocket("/ws/events")
    async def events(websocket: WebSocket):
        await websocket.accept()
        queue = event_bus.subscribe()
        try:
            await websocket.send_json({
                "event_type": "CONNECTED",
                "account_id": None,
                "payload": {"subscriber_count": event_bus.subscriber_count},
            })
            while True:
                event = await queue.get()
                await websocket.send_json(event_bus.serialize(event))
        except WebSocketDisconnect:
            pass
        finally:
            event_bus.unsubscribe(queue)
