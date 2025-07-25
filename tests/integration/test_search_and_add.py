# -*- coding: utf-8 -*-
import pytest
from unittest.mock import AsyncMock, Mock, patch, PropertyMock

from app.handlers.search import handle_text_message, add_word_to_dictionary
from dal.repositories import WordRepository, UserDictionaryRepository
from tests.integration.conftest import TEST_USER_ID

@pytest.mark.asyncio
@pytest.mark.usefixtures("init_db_for_test")
@patch("app.handlers.search.fetch_and_cache_word_data")
async def test_search_and_add_flow(mock_fetch_and_cache):
    """Full E2E test for the 'search and add' flow."""
    # 1. Мокаем все внешние зависимости
    mock_update = Mock()
    mock_context = AsyncMock()

    # Мокаем сообщение пользователя
    user_message_text = "בדיקה"
    mock_update.message = AsyncMock()
    mock_update.message.text = user_message_text
    type(mock_update).effective_user = PropertyMock(return_value=Mock(id=TEST_USER_ID))
    type(mock_update).effective_chat = PropertyMock(return_value=Mock(id=12345))

    # Мокаем ответ бота, чтобы сохранить message_id
    mock_reply = AsyncMock()
    mock_reply.message_id = 98765
    mock_update.message.reply_text.return_value = mock_reply

    # Настраиваем мок-ответ от fetch_and_cache_word_data
    mock_fetch_and_cache.return_value = ("ok", {
        "word_id": 1,
        "hebrew": "בדיקה",
        "transcription": "bdika",
        "translations": [{"translation_text": "проверка, тест", "is_primary": True}],
        "is_verb": False,
        "root": None,
        "binyan": None,
        "conjugations": [],
        "normalized_hebrew": "בדיקה"
    })

    # 2. Вызываем обработчик
    await handle_text_message(mock_update, mock_context)

    # 3. Проверяем, что fetch_and_cache_word_data была вызвана
    mock_fetch_and_cache.assert_called_once_with(user_message_text)

    # 4. Проверяем, что карточка слова была отправлена
    mock_context.bot.edit_message_text.assert_called_once()
    call_args, call_kwargs = mock_context.bot.edit_message_text.call_args

    # Проверяем текст ответа
    assert "проверка, тест" in call_kwargs['text']
    assert "bdika" in call_kwargs['text']

    # Проверяем, что кнопка "Добавить" на месте
    reply_markup = call_kwargs['reply_markup']
    add_button = reply_markup.inline_keyboard[0][0]
    assert "Добавить" in add_button.text

    # 5. Симулируем нажатие кнопки "Добавить"
    mock_query = AsyncMock()
    type(mock_query).data = PropertyMock(return_value=f"add:word:{mock_fetch_and_cache.return_value[1]['word_id']}")
    type(mock_query).from_user = PropertyMock(return_value=Mock(id=TEST_USER_ID))
    mock_update.callback_query = mock_query

    # Mock the database calls for add_word_to_dictionary
    with patch("app.handlers.search.word_repo.get_word_by_id") as mock_get_word_by_id, \
         patch("app.handlers.search.user_dict_repo.add_word_to_dictionary") as mock_add_word:

        mock_get_word_by_id.return_value = Mock(
            word_id=1,
            hebrew="בדיקה",
            transcription="bdika",
            translations=[{"translation_text": "проверка, тест", "is_primary": True}],
            is_verb=False,
            root=None,
            binyan=None,
            conjugations=[],
            normalized_hebrew="בדיקה",
            model_dump=lambda: {
                "word_id": 1,
                "hebrew": "בדיקה",
                "transcription": "bdika",
                "translations": [{"translation_text": "проверка, тест", "is_primary": True}],
                "is_verb": False,
                "root": None,
                "binyan": None,
                "conjugations": [],
                "normalized_hebrew": "בדיקה"
            }
        )

        await add_word_to_dictionary(mock_update, mock_context)

        # 6. Проверяем, что слово было добавлено в словарь пользователя
        mock_add_word.assert_called_once_with(TEST_USER_ID, 1)

        # 7. Проверяем, что карточка слова обновилась
        assert mock_context.bot.edit_message_text.call_count == 2
        call_args, call_kwargs = mock_context.bot.edit_message_text.call_args

        reply_markup = call_kwargs['reply_markup']
        first_button = reply_markup.inline_keyboard[0][0]
        assert "Удалить" in first_button.text
