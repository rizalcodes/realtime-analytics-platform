"""Push updates to connected WebSocket clients via Redis pub/sub.

Source of truth for what gets broadcast:

Channel:
    analytics:updates

Message shape (JSON):
    {
        "event": "<event type, e.g. 'new_order'>",
        "timestamp": "<ISO 8601 UTC>",
        "payload": { ...event-specific data... }
    }

Flow: anything (this app or a separate process) calls publish_event() ->
Redis pub/sub -> redis_listener() (one task, started in the app lifespan)
-> ConnectionManager.broadcast() -> every connected WebSocket client.
A dropped client never crashes the broadcaster or affects other clients.
"""

import asyncio
import json
import os
from contextlib import suppress
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import WebSocket

from realtime.redis_client import get_redis

CHANNEL = "analytics:updates"


class ConnectionManager:
    """Tracks currently-connected WebSocket clients."""

    def __init__(self) -> None:
        self.active: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active.discard(websocket)

    async def broadcast(self, message: str) -> None:
        """Send `message` to all connected clients; drop any that fail."""
        for websocket in list(self.active):
            try:
                await websocket.send_text(message)
            except Exception:
                self.disconnect(websocket)


manager = ConnectionManager()


def publish_event(event: str, payload: dict) -> dict:
    """Publish an event to the Redis channel; returns the message that was sent."""
    message = {
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    get_redis().publish(CHANNEL, json.dumps(message))
    return message


async def redis_listener(ready: asyncio.Event | None = None) -> None:
    """Subscribe to the Redis channel and broadcast every message to all clients.

    Runs as a single background task for the app's lifetime (started in the
    FastAPI lifespan). Sets `ready` once the subscription is established.
    """
    client = aioredis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        decode_responses=True,
    )
    pubsub = client.pubsub()
    await pubsub.subscribe(CHANNEL)
    if ready is not None:
        ready.set()
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await manager.broadcast(message["data"])
    finally:
        with suppress(Exception):
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()
            await client.aclose()
