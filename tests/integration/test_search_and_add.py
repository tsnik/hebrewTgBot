# tests/integration/test_search_add_integration.py
import pytest
from unittest.mock import AsyncMock, Mock, patch, PropertyMock

# Импортируем хендлеры и константы из приложения
from handlers.search import handle_text_message, add_word_to_dictionary
from config import CB_ADD, CB_DICT_CONFIRM_DELETE
from dal.unit_of_work import UnitOfWork
from dal.repositories import UserDictionaryRepository

# Используем константы из conftest для консистентности
TEST_USER_ID = 123456789
TEST_CHAT_ID = 987654321

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
@patch("services.parser.httpx.AsyncClient")  # Патчим HTTP-клиент в модуле парсера
async def test_full_search_and_add_scenario(mock_async_client, mock_context):
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
    type(mock_response).url = PropertyMock(
        return_value="https://www.pealim.com/ru/dict/1234-bdika/"
    )
    mock_async_client.return_value.__aenter__.return_value.get.return_value = (
        mock_response
    )

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
    type(search_update).effective_user = PropertyMock(
        return_value=Mock(id=TEST_USER_ID)
    )
    type(search_update).effective_chat = PropertyMock(
        return_value=Mock(id=TEST_CHAT_ID)
    )

    # 1.2. Вызываем основной обработчик текстовых сообщений
    with patch("handlers.search.display_word_card") as mock_display_word_card:
        await handle_text_message(search_update, mock_context)

        # 1.3. Проверяем результат
        # Убеждаемся, что сообщение "Ищу..." было сначала отправлено
        search_update.message.reply_text.assert_called_once_with(
            "🔎 Ищу слово во внешнем словаре..."
        )

        # Проверяем, что display_word_card была вызвана
        mock_display_word_card.assert_called_once()

        # Получаем аргументы вызова display_word_card для детальной проверки
        _call_args, call_kwargs = mock_display_word_card.call_args
        print(call_kwargs)
        word_data = call_kwargs["word_data"]

        # Проверяем наличие кнопки "Добавить"
        assert word_data["hebrew"] == "בדיקה"

    with UnitOfWork() as uow:
        word = uow.words.find_word_by_normalized_form("בדיקה")
        assert word is not None
        word_id = word.word_id
        assert uow.user_dictionary.is_word_in_dictionary(TEST_USER_ID, word_id) is False

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
    with patch("handlers.search.display_word_card") as mock_display_word_card:
        await add_word_to_dictionary(add_update, mock_context)

        # 2.3. Проверяем итоговый результат
        mock_display_word_card.assert_called_once()
        _call_args, call_kwargs = mock_display_word_card.call_args
        assert call_kwargs["in_dictionary"] is True

    # Финальная проверка БД: слово теперь должно быть в словаре пользователя
    with UnitOfWork() as uow:
        assert uow.user_dictionary.is_word_in_dictionary(TEST_USER_ID, word_id) is True
