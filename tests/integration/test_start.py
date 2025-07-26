import pytest
from unittest.mock import AsyncMock, Mock, PropertyMock, patch
from handlers.common import start
from dal.unit_of_work import UnitOfWork

@pytest.mark.asyncio
async def test_start_command():
    """Test the /start command."""
    update = Mock()
    update.message = AsyncMock()
    type(update).effective_user = PropertyMock(return_value=Mock(id=123, first_name="Test", username="testuser"))
    context = Mock()
    context.bot = AsyncMock()

    with patch('handlers.common.UnitOfWork'):
        await start(update, context)

    update.message.reply_text.assert_called_once()
    assert "Привет, Test!" in update.message.reply_text.call_args[0][0]
