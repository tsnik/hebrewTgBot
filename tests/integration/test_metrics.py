import pytest
from unittest.mock import AsyncMock
from prometheus_client import CollectorRegistry
from telegram import Update


@pytest.mark.asyncio
async def test_message_counter(monkeypatch):
    """Test that the message counter is incremented."""
    from app.metrics import MESSAGES_COUNTER
    from app.handlers.search import handle_text_message

    monkeypatch.setattr("app.handlers.search.search_in_pealim", AsyncMock())
    initial_messages = MESSAGES_COUNTER._value.get()
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
    assert MESSAGES_COUNTER._value.get() == initial_messages + 1


@pytest.mark.asyncio
async def test_callback_counter():
    """Test that the callback counter is incremented."""
    from app.metrics import CALLBACKS_COUNTER
    from app.handlers.common import main_menu

    initial_callbacks = CALLBACKS_COUNTER._value.get()
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
    assert CALLBACKS_COUNTER._value.get() == initial_callbacks + 1
