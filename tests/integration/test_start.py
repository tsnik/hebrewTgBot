import pytest
from unittest.mock import AsyncMock, Mock, PropertyMock
from handlers.common import start


@pytest.mark.asyncio
async def test_start_command(memory_db):
    """Test the /start command."""
    update = Mock()
    update.message = AsyncMock()
    type(update).effective_user = PropertyMock(
        return_value=Mock(id=123, first_name="Test", username="testuser")
    )
    context = Mock()
    context.bot = AsyncMock()

    await start(update, context)

    update.message.reply_text.assert_called_once()
    assert "Привет, Test!" in update.message.reply_text.call_args[0][0]
