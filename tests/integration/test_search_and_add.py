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
    # ... (эта часть остается без изменений) ...
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

    # --- 2. Подготовка мока для HTTP-запроса (ИСПРАВЛЕННАЯ ЧАСТЬ) ---
    with open("tests/fixtures/search_word.html", "r", encoding="utf-8") as f:
        html_content = f.read()

    # Создаем мок для объекта Response
    mock_response = Mock()
    # Используем PropertyMock, чтобы .text вел себя как обычное свойство, а не корутина
    type(mock_response).text = PropertyMock(return_value=html_content)
    mock_response.status_code = 200
    # Метод raise_for_status() у реального ответа не является async
    mock_response.raise_for_status = Mock()

    # Создаем мок для клиента
    mock_async_client = AsyncMock()
    # Настраиваем метод get() так, чтобы он возвращал наш подготовленный mock_response
    mock_async_client.get.return_value = mock_response

    # Подменяем httpx.AsyncClient в модуле парсера
    monkeypatch.setattr("app.services.parser.httpx.AsyncClient", lambda **kwargs: mock_async_client)

    # --- 3. Вызываем обработчик ---
    await handle_text_message(mock_update, mock_context)

    # --- 4. Проверяем состояние БД ---
    word_repo = WordRepository()
    normalized_form = normalize_hebrew(user_message_text)
    new_word = word_repo.find_word_by_normalized_form(normalized_form)
    
    # Теперь эта проверка должна пройти
    assert new_word is not None
    # ... (остальные проверки) ...
    assert new_word.hebrew == "בדיקה"
    assert new_word.transcription == "bdika"
    assert "проверка" in new_word.translations[0].translation_text

    # ... (остальная часть теста без изменений) ...
    # --- 5. Проверяем, что карточка слова была отправлена пользователю ---
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
    delete_button = final_card_kwargs['reply
