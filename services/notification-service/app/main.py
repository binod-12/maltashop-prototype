import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .common import mq
from .common.db import mark_processed, open_db, query_all, tx
from .common.log import info
from .templates import TEMPLATES

PORT = int(os.environ.get("PORT", "3004"))
DB_PATH = os.environ.get("DB_PATH", "./data/notifications.db")

db = open_db(
    DB_PATH,
    """CREATE TABLE IF NOT EXISTS notifications (
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         order_id TEXT NOT NULL,
         kind TEXT NOT NULL,
         body TEXT NOT NULL,
         correlation_id TEXT,
         sent_at TEXT NOT NULL
       );""",
)


async def on_event(payload: dict, meta: mq.Meta) -> None:
    """Notification is a pure subscriber. If it is slow or crashes, checkout is unaffected:
    messages simply wait in its durable queue (the March memory-leak incident cannot recur this way)."""
    cid = meta.correlation_id
    info("event.received", f"received {meta.routing_key}", cid, orderId=payload["orderId"])

    with tx(db):
        fresh = mark_processed(db, meta.message_id, f"notify.{meta.routing_key}")
    if not fresh:
        info("event.duplicate", "duplicate event ignored - no second email", cid)
        return

    body = TEMPLATES[meta.routing_key](payload)
    db.execute(
        "INSERT INTO notifications (order_id, kind, body, correlation_id, sent_at) VALUES (?, ?, ?, ?, ?)",
        (payload["orderId"], meta.routing_key, body, cid, datetime.now(UTC).isoformat()),
    )
    info("notification.sent", f"EMAIL (simulated): {body}", cid, orderId=payload["orderId"])


async def setup() -> None:
    try:
        await mq.connect()
        await mq.subscribe("notification-service.events", ["order.placed", "order.confirmed", "order.cancelled"], on_event)
    except Exception as exc:  # noqa: BLE001
        print(f"fatal: {exc}", flush=True)
        os._exit(1)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(setup())
    info("service.started", f"notification-service listening on {PORT}")
    yield
    task.cancel()
    await mq.close()


app = FastAPI(title="notification-service", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    if mq.is_connected():
        return {"status": "ready"}
    return JSONResponse({"status": "broker-unavailable"}, status_code=503)


@app.get("/notifications")
async def notifications():
    return query_all(db, "SELECT * FROM notifications ORDER BY id")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_config=None, access_log=False)
