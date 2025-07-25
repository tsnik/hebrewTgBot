# tests/integration/test_search_add_integration.py
import pytest
from unittest.mock import AsyncMock, Mock, patch, PropertyMock

# Импортируем хендлеры и константы из приложения
from app.handlers.search import handle_text_message, add_word_to_dictionary
from app.config import CB_ADD, CB_DICT_CONFIRM_DELETE
from app.dal.repositories import UserDictionaryRepository

# Используем константы из conftest для консистентности
from .conftest import TEST_USER_ID, TEST_CHAT_ID

# Мок HTML-ответа от pealim.com для слова "בדיקה"
# Он содержит минимально необходимую структуру для успешного парсинга
MOCK_PEALIM_HTML = """
<html>
<head><title>בדיקה – pealim.com</title></head>
<body>
    <h2 class="page-header">בדיקה</h2>
    <div class="transcription">bdika</div>
    <div class="lead">проверка, тест; анализ</div>
</body>
</html>
"""

@pytest.mark.asyncio
@patch("app.services.parser.httpx.AsyncClient")  # Патчим HTTP-клиент в модуле парсера
async def test_full_search_and_add_scenario(mock_async_client, test_db, mock_context):
    """
    Полный интеграционный тест сценария:
    1. Пользователь ищет слово, которого нет в кэше.
    2. Слово парсится с внешнего ресурса (используя мок HTTP) и сохраняется в БД.
    3. Пользователю отображается карточка с кнопкой "Добавить".
    4. Пользователь нажимает "Добавить".
    5. Слово добавляется в его личный словарь в БД.
    6. Карточка обновляется, показывая кнопку "Удалить".
    """
    # --- Подготовка моков ---
    # Настраиваем мок HTTP-клиента, чтобы он возвращал наш тестовый HTML
    mock_response = Mock()
    mock_response.text = MOCK_PEALIM_HTML
    mock_response.status_code = 200
    # Парсер следует редиректам, поэтому мокаем итоговый URL
    type(mock_response).url = PropertyMock(return_value="https://www.pealim.com/ru/dict/1234-bdika/")
    mock_async_client.return_value.__aenter__.return_value.get.return_value = mock_response

    # ============================================
    # --- Часть 1: Поиск нового слова ---
    # ============================================

    # 1.1. Симулируем отправку сообщения пользователем
    search_update = Mock()
    user_message_text = "בדיקה"
    search_update.message = AsyncMock()
    search_update.message.text = user_message_text
    # Мокаем ответ "Ищу слово..."
    search_update.message.reply_text.return_value = AsyncMock(message_id=111)
    type(search_update).effective_user = PropertyMock(return_value=Mock(id=TEST_USER_ID))
    type(search_update).effective_chat = PropertyMock(return_value=Mock(id=TEST_CHAT_ID))

    # 1.2. Вызываем основной обработчик текстовых сообщений
    await handle_text_message(search_update, mock_context)

    # 1.3. Проверяем результат
    # Убеждаемся, что сообщение "Ищу..." было сначала отправлено, а затем отредактировано
    search_update.message.reply_text.assert_called_once_with("🔎 Ищу слово во внешнем словаре...")
    mock_context.bot.edit_message_text.assert_called_once()

    # Получаем аргументы вызова edit_message_text для детальной проверки
    _call_args, call_kwargs = mock_context.bot.edit_message_text.call_args

    # Проверяем текст итоговой карточки
    assert "Найдено: *בדיקה*" in call_kwargs['text']
    assert "[bdika]" in call_kwargs['text']
    assert "тест" in call_kwargs['text']
    assert "проверка" in call_kwargs['text']

    # Проверяем наличие кнопки "Добавить"
    reply_markup = call_kwargs['reply_markup']
    add_button = reply_markup.inline_keyboard[0][0]
    assert "➕ Добавить" in add_button.text

    # Проверяем состояние БД: слово должно быть в общем кэше, но не в словаре пользователя
    cursor = test_db.cursor()
    cursor.execute("SELECT word_id FROM cached_words WHERE hebrew = ?", (user_message_text,))
    word_row = cursor.fetchone()
    assert word_row is not None, "Слово должно было быть сохранено в таблицу 'cached_words'"
    word_id = word_row['word_id']

    # Убеждаемся, что callback-данные кнопки содержат правильный ID слова
    assert add_button.callback_data == f"{CB_ADD}:{word_id}"

    # Проверяем через репозиторий, что слова еще нет в словаре пользователя
    user_repo = UserDictionaryRepository()
    in_dict = user_repo.is_word_in_dictionary(TEST_USER_ID, word_id)
    assert not in_dict, "Слово не должно быть в словаре пользователя на этом этапе"

    # =======================================================
    # --- Часть 2: Добавление слова в личный словарь ---
    # =======================================================

    # 2.1. Симулируем нажатие пользователем кнопки "Добавить"
    add_update = Mock()
    mock_query = AsyncMock()
    # Важно мокировать и сообщение внутри query, т.к. хендлер использует его chat_id и message_id
    mock_query.message = AsyncMock(chat_id=TEST_CHAT_ID, message_id=111)
    type(add_update).callback_query = mock_query
    type(mock_query).data = PropertyMock(return_value=f"{CB_ADD}:{word_id}")
    type(mock_query).from_user = PropertyMock(return_value=Mock(id=TEST_USER_ID))

    # 2.2. Вызываем обработчик добавления слова
    await add_word_to_dictionary(add_update, mock_context)

    # 2.3. Проверяем итоговый результат
    # Убеждаемся, что бот второй раз отредактировал сообщение (обновил карточку)
    assert mock_context.bot.edit_message_text.call_count == 2, "Карточка слова должна была обновиться"

    # Получаем аргументы второго вызова
    _call_args, call_kwargs = mock_context.bot.edit_message_text.call_args

    # Проверяем, что текст карточки изменился
    assert f"Слово *{user_message_text}* уже в вашем словаре." in call_kwargs['text']

    # Проверяем, что кнопка "Добавить" сменилась на "Удалить"
    reply_markup = call_kwargs['reply_markup']
    delete_button = reply_markup.inline_keyboard[0][0]
    assert "🗑️ Удалить" in delete_button.text
    assert delete_button.callback_data == f"{CB_DICT_CONFIRM_DELETE}:{word_id}:0"

    # Финальная проверка БД: слово теперь должно быть в словаре пользователя
    in_dict_after_add = user_repo.is_word_in_dictionary(TEST_USER_ID, word_id)
    assert in_dict_after_add, "Слово должно было появиться в словаре пользователя"
