import pytest
from unittest.mock import AsyncMock
from telegram import Update
from prometheus_client import CollectorRegistry
from app.metrics import create_counters
from app.handlers.search import handle_text_message
from app.handlers.common import main_menu


@pytest.mark.asyncio
async def test_message_counter(monkeypatch):
    """Test that the message counter is incremented."""
    registry = CollectorRegistry()
    messages_counter, _ = create_counters(registry)
    monkeypatch.setattr("app.handlers.search.MESSAGES_COUNTER", messages_counter)

    initial_messages = messages_counter._value.get()
    bot = AsyncMock()
    bot.get_me = AsyncMock(return_value=None)
    bot.defaults.tzinfo = None
    update = Update.de_json(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 1,
                "chat": {"id": 1, "type": "private"},
                "text": "hello",
                "from": {"id": 1, "is_bot": False, "first_name": "test"},
            },
        },
        bot,
    )
    mock_context = AsyncMock()
    mock_context.bot = bot
    await handle_text_message(update, mock_context)
    assert messages_counter._value.get() == initial_messages + 1


@pytest.mark.asyncio
async def test_callback_counter(monkeypatch):
    """Test that the callback counter is incremented."""
    registry = CollectorRegistry()
    _, callbacks_counter = create_counters(registry)
    monkeypatch.setattr("app.bot.CALLBACKS_COUNTER", callbacks_counter)

    initial_callbacks = callbacks_counter._value.get()
    bot = AsyncMock()
    bot.get_me = AsyncMock(return_value=None)
    bot.defaults.tzinfo = None
    update = Update.de_json(
        {
            "update_id": 2,
            "callback_query": {
                "id": "1",
                "from": {"id": 1, "is_bot": False, "first_name": "test"},
                "message": {
                    "message_id": 1,
                    "date": 1,
                    "chat": {"id": 1, "type": "private"},
                    "text": "hello",
                },
                "chat_instance": "1",
                "data": "main_menu",
            },
        },
        bot,
    )
    mock_context = AsyncMock()
    mock_context.bot = bot
    await main_menu(update, mock_context)
    assert callbacks_counter._value.get() == initial_callbacks + 1
