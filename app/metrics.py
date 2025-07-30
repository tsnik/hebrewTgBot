# -*- coding: utf-8 -*-

from functools import wraps
from prometheus_client import Counter


def create_counters(registry):
    """Create the Prometheus counters."""
    messages_counter = Counter(
        "bot_messages_total",
        "Total number of messages received by the bot",
        registry=registry,
    )
    callbacks_counter = Counter(
        "bot_callbacks_total",
        "Total number of callback queries received by the bot",
        registry=registry,
    )
    return messages_counter, callbacks_counter


def increment_callbacks_counter(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        from app.bot import CALLBACKS_COUNTER
        CALLBACKS_COUNTER.inc()
        return await func(*args, **kwargs)

    return wrapper
