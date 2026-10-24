"""Relay server-sent events agar browser menerima harga tanpa polling."""
import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from backend.market_stream import market_stream

router = APIRouter(tags=["Real-time Market"])


@router.get("/api/market/stream")
async def stream_market(request: Request):
    async def events():
        queue = market_stream.subscribe()
        try:
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if event["type"] == "overflow":
                    break
                yield f"data: {json.dumps(event, allow_nan=False)}\n\n"
        finally:
            await market_stream.unsubscribe(queue)

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })
