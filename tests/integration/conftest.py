# tests/conftest.py
import pytest
import asyncio
from unittest.mock import AsyncMock


TEST_USER_ID = 123456789
TEST_CHAT_ID = 987654321


@pytest.fixture(scope="session")
def event_loop():
    """Создает экземпляр цикла событий по умолчанию для каждой тестовой сессии."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_context():
    """Создает мок объекта context для Telegram."""
    context = AsyncMock()
    context.bot.send_message.return_value = AsyncMock(message_id=111)
    context.bot.edit_message_text.return_value = AsyncMock(message_id=111)
    return context
