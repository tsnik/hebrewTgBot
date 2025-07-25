import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.handlers.common import start, main_menu
from app.handlers.dictionary import view_dictionary_page_handler
from app.handlers.search import handle_text_message
from app.services.parser import fetch_and_cache_word_data

@pytest.mark.asyncio
async def test_start():
    update = AsyncMock()
    update.effective_user.first_name = "Test"
    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await start(update, context)

    update.message.reply_text.assert_called_once()
    assert "Привет, Test!" in update.message.reply_text.call_args.args[0]

@pytest.mark.asyncio
async def test_main_menu():
    update = AsyncMock()
    context = MagicMock()

    await main_menu(update, context)

    update.callback_query.answer.assert_called_once()
    update.callback_query.edit_message_text.assert_called_once()
    assert "Главное меню" in update.callback_query.edit_message_text.call_args.args[0]

@pytest.mark.asyncio
async def test_view_dictionary_page_handler():
    update = AsyncMock()
    update.callback_query.data = "dict:view:0"
    update.callback_query.from_user.id = 123
    context = MagicMock()

    with patch('app.handlers.dictionary.user_dict_repo') as mock_repo:
        mock_repo.get_dictionary_page.return_value = []
        await view_dictionary_page_handler(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "Ваш словарь пуст" in update.callback_query.edit_message_text.call_args.args[0]

@pytest.mark.asyncio
async def test_handle_text_message():
    update = AsyncMock()
    update.message.text = "שלום"
    context = MagicMock()

    with patch('app.handlers.search.word_repo') as mock_repo:
        mock_repo.find_word_by_normalized_form.return_value = MagicMock(
            dict=MagicMock(return_value={'hebrew': 'שלום', 'translations': [{'translation_text': 'hello'}]})
        )
        with patch('app.handlers.search.display_word_card') as mock_display:
            await handle_text_message(update, context)

    mock_display.assert_called_once()
