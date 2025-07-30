# -*- coding: utf-8 -*-

from functools import wraps
from prometheus_client import Counter

MESSAGES_COUNTER = Counter(
    "bot_messages_total", "Total number of messages received by the bot"
)
CALLBACKS_COUNTER = Counter(
    "bot_callbacks_total", "Total number of callback queries received by the bot"
)


def increment_callbacks_counter(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        CALLBACKS_COUNTER.inc()
        return await func(*args, **kwargs)

    return wrapper
