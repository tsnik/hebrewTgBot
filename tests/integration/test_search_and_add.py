# -*- coding: utf-8 -*-
import pytest
from unittest.mock import AsyncMock, Mock, PropertyMock

from app.handlers.search import handle_text_message, add_word_to_dictionary
from dal.repositories import WordRepository, UserDictionaryRepository
from tests.integration.conftest import TEST_USER_ID
from app.utils import normalize_hebrew

@pytest.mark.asyncio
@pytest.mark.usefixtures("init_db_for_test")
async def test_search_and_add_flow_e2e(monkeypatch):
    """
    Полный E2E тест для флоу 'поиск-парсинг-сохранение-добавление'.
    Этот тест НЕ мокает сервис парсинга, а мокает только HTTP-запрос.
    """
    # --- 1. Подготовка моков для Telegram ---
    mock_update = Mock()
    mock_context = AsyncMock()
    
    user_message_text = "בדיקה"
    mock_update.message = AsyncMock()
    mock_update.message.text = user_message_text
    type(mock_update).effective_user = PropertyMock(return_value=Mock(id=TEST_USER_ID))
    type(mock_update).effective_chat = PropertyMock(return_value=Mock(id=12345))

    mock_reply = AsyncMock()
    mock_reply.message_id = 98765
    mock_update.message.reply_text.return_value = mock_reply
    
        # --- 2. Подготовка мока для HTTP-запроса ---
    with open("tests/fixtures/search_word.html", "r", encoding="utf-8") as f:
        html_content = f.read()

    # Создаем мок для объекта ответа httpx
    mock_response = Mock()
    # Устанавливаем атрибут .text напрямую, чтобы избежать его преобразования в корутину.
    mock_response.text = html_content
    mock_response.status_code = 200
    # Парсер проверяет URL, чтобы определить, было ли прямое перенаправление на страницу слова.
    # Наша фикстура - это и есть страница слова, поэтому мокируем URL соответствующим образом.
    mock_response.url = "https://www.pealim.com/ru/dict/123-test/"
    # raise_for_status - это обычный метод, а не корутина.
    mock_response.raise_for_status = Mock()

    # Создаем мок для асинхронного клиента httpx
    mock_async_client = AsyncMock()
    # Метод .get() должен возвращать наш подготовленный мок ответа.
    mock_async_client.get.return_value = mock_response

    monkeypatch.setattr("app.services.parser.httpx.AsyncClient", lambda **kwargs: mock_async_client)

    # --- 3. Вызываем обработчик ---
    await handle_text_message(mock_update, mock_context)

    # --- 4. Проверяем состояние БД ---
    word_repo = WordRepository()
    normalized_form = normalize_hebrew(user_message_text)
    new_word = word_repo.find_word_by_normalized_form(normalized_form)
    
    assert new_word is not None
    assert new_word.hebrew == "בדיקה"
    assert new_word.transcription == "bdika"
    assert "проверка" in new_word.translations[0].translation_text

    # --- 5. Проверяем, что карточка слова была отправлена ---
    mock_context.bot.edit_message_text.assert_called_once()
    _, call_kwargs = mock_context.bot.edit_message_text.call_args
    
    assert "Найдено: *בדיקה*" in call_kwargs['text']
    add_button = call_kwargs['reply_markup'].inline_keyboard[0][0]
    assert "Добавить" in add_button.text
    
    # --- 6. Симулируем нажатие кнопки "Добавить" ---
    add_update = AsyncMock()
    add_update.callback_query.data = f"word:add:{new_word.word_id}"
    add_update.callback_query.from_user.id = TEST_USER_ID
    add_update.callback_query.message = mock_reply 

    await add_word_to_dictionary(add_update, mock_context)
    
    # --- 7. Проверяем финальное состояние БД ---
    user_dict_repo = UserDictionaryRepository()
    user_words = user_dict_repo.get_dictionary_page(TEST_USER_ID, 0, 1)
    
    assert len(user_words) == 1
    assert user_words[0]['word_id'] == new_word.word_id
    
    # --- 8. Проверяем, что карточка слова обновилась ---
    assert mock_context.bot.edit_message_text.call_count == 2
    _, final_card_kwargs = mock_context.bot.edit_message_text.call_args
    
    assert "уже в вашем словаре" in final_card_kwargs['text']
    delete_button = final_card_kwargs['reply_markup'].inline_keyboard[0][0]
    assert "Удалить" in delete_button.text