from app.realtime.broadcaster import RESYNC, Broadcaster


def test_scoped_subscriptions_only_receive_matching_events():
    b = Broadcaster()
    everything = b.subscribe()
    order = b.subscribe(order_id=1)
    position = b.subscribe(position_id=10)

    b.publish({"id": 1, "order_id": 1, "position_id": 10})
    b.publish({"id": 2, "order_id": 2, "position_id": 20})

    assert everything.queue.qsize() == 2
    assert order.queue.get_nowait()["id"] == 1 and order.queue.empty()
    assert position.queue.get_nowait()["id"] == 1 and position.queue.empty()


def test_resync_reaches_every_subscriber():
    b = Broadcaster()
    subs = [b.subscribe(), b.subscribe(order_id=5)]
    b.publish_resync()
    assert all(s.queue.get_nowait() is RESYNC for s in subs)


def test_slow_subscriber_is_dropped():
    b = Broadcaster()
    slow = b.subscribe()
    for i in range(slow.queue.maxsize + 1):
        b.publish({"id": i})
    assert slow.overflowed
    assert b.subscriber_count == 0
