from app.metrics import create_counters
from prometheus_client import REGISTRY

MESSAGES_COUNTER, CALLBACKS_COUNTER = create_counters(REGISTRY)
