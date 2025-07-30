# -*- coding: utf-8 -*-

from functools import wraps
from prometheus_client import Counter, REGISTRY


def create_metric(metric_class, name, documentation, labelnames=()):
    """
    Создает метрику, если она еще не существует, иначе возвращает существующую.
    Это предотвращает ошибки 'Duplicated timeseries' при повторных импортах.
    """
    if name in REGISTRY._names_to_collectors:
        # Получаем существующую метрику из реестра
        metric = REGISTRY._names_to_collectors[name]
    else:
        # Создаем новую метрику, если ее нет
        metric = metric_class(name, documentation, labelnames, registry=REGISTRY)
    return metric


# --- Определяем наши метрики с помощью новой функции ---

MESSAGES_COUNTER = create_metric(
    Counter, "bot_messages_total", "Total number of messages received by the bot"
)

CALLBACKS_COUNTER = create_metric(
    Counter,
    "bot_callbacks_total",
    "Total number of callback queries received by the bot",
)

# --- Декораторы остаются без изменений ---


def increment_callbacks_counter(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        CALLBACKS_COUNTER.inc()
        return await func(*args, **kwargs)

    return wrapper


def increment_messages_counter(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        MESSAGES_COUNTER.inc()
        return await func(*args, **kwargs)

    return wrapper
