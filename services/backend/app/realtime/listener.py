"""One dedicated LISTEN connection per API process, feeding the broadcaster."""

import asyncio
import json
import logging

import psycopg
from psycopg import sql

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.orchestration import Event
from app.realtime.broadcaster import Broadcaster
from app.realtime.events import serialize_event

logger = logging.getLogger(__name__)


class EventListener:
    def __init__(self, broadcaster: Broadcaster) -> None:
        settings = get_settings()
        self._conninfo = settings.psycopg_conninfo
        self._channel = settings.EVENTS_CHANNEL
        self._broadcaster = broadcaster
        self._task: asyncio.Task | None = None
        self.connected = False

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="events-listener")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        backoff = 1.0
        first = True
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(
                    self._conninfo, autocommit=True
                ) as conn:
                    await conn.execute(sql.SQL("LISTEN {}").format(sql.Identifier(self._channel)))
                    self.connected = True
                    backoff = 1.0
                    logger.info("Listening on channel %s", self._channel)
                    if not first:
                        self._broadcaster.publish_resync()
                    first = False
                    async for notify in conn.notifies():
                        await self._handle(notify.payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Events listener lost its connection; retrying in %.0fs", backoff)
            self.connected = False
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    async def _handle(self, payload: str) -> None:
        try:
            event_id = json.loads(payload)["id"]
            # The NOTIFY payload carries ids only; load the full row once for all subscribers.
            async with AsyncSessionLocal() as session:
                event = await session.get(Event, event_id)
            if event is not None:
                self._broadcaster.publish(serialize_event(event))
        except Exception:
            logger.exception("Could not handle notification %s", payload)
