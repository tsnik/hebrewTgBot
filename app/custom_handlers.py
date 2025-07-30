# -*- coding: utf-8 -*-

from telegram.ext import CallbackQueryHandler
from metrics import CALLBACKS_COUNTER


class InstrumentedCallbackQueryHandler(CallbackQueryHandler):
    def check_update(self, update):
        if super().check_update(update):
            CALLBACKS_COUNTER.inc()
            return True
        return False
