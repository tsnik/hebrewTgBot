# app/context.py
import logging
from contextvars import ContextVar

# 1. Определяем ContextVar здесь, в независимом файле.
request_id_var = ContextVar("request_id", default="-")
username_var = ContextVar("username", default="-")
handler_name_var = ContextVar("handler_name", default="-")


# 2. Фильтр логгера тоже здесь. Он зависит только от ContextVar.
class RequestIdFilter(logging.Filter):
    """
    Этот фильтр добавляет request_id из ContextVar в каждую запись лога.
    """

    def filter(self, record):
        record.request_id = request_id_var.get()
        record.username = username_var.get()
        record.handler_name = handler_name_var.get()
        return True
