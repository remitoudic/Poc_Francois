"""In-process fan-out of events to SSE subscribers, filtered by scope."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

RESYNC = {"type": "resync"}


@dataclass(eq=False)
class Subscription:
    order_id: int | None = None
    position_id: int | None = None
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=1000))
    overflowed: bool = False

    def matches(self, event: dict[str, Any]) -> bool:
        if self.position_id is not None:
            return event.get("position_id") == self.position_id
        if self.order_id is not None:
            return event.get("order_id") == self.order_id
        return True


class Broadcaster:
    def __init__(self) -> None:
        self._subscriptions: set[Subscription] = set()

    def subscribe(
        self, order_id: int | None = None, position_id: int | None = None
    ) -> Subscription:
        subscription = Subscription(order_id=order_id, position_id=position_id)
        self._subscriptions.add(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        self._subscriptions.discard(subscription)

    def publish(self, event: dict[str, Any]) -> None:
        for subscription in list(self._subscriptions):
            if subscription.matches(event):
                self._put(subscription, event)

    def publish_resync(self) -> None:
        """Tell every client it may have missed events (listener reconnected)."""
        for subscription in list(self._subscriptions):
            self._put(subscription, RESYNC)

    def _put(self, subscription: Subscription, item: dict[str, Any]) -> None:
        try:
            subscription.queue.put_nowait(item)
        except asyncio.QueueFull:
            # Slow client: its stream closes, and the browser reconnects with Last-Event-ID.
            subscription.overflowed = True
            self.unsubscribe(subscription)
            logger.warning("Dropped slow SSE subscriber")

    @property
    def subscriber_count(self) -> int:
        return len(self._subscriptions)


broadcaster = Broadcaster()
