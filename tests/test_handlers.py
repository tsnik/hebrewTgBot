import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

# Эти импорты верны, так как они отражают структуру вашего проекта
from dal.models import CachedWord, Translation
from handlers.common import start, main_menu
from handlers.dictionary import view_dictionary_page_handler, confirm_delete_word, execute_delete_word
from handlers.search import handle_text_message, add_word_to_dictionary, show_verb_conjugations, view_word_card_handler
from handlers.training import training_menu, start_flashcard_training, show_answer, handle_self_evaluation, start_verb_trainer


# --- Тесты для общих обработчиков (не требуют патчинга БД) ---

@pytest.mark.asyncio
async def test_start():
    update = AsyncMock()
    update.effective_user.first_name = "Test"
    update.effective_user.id = 123
    update.effective_user.username = "testuser"
    context = MagicMock()

    # ИСПРАВЛЕНИЕ: убран префикс 'app.'
    with patch('handlers.common.UnitOfWork') as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value

        await start(update, context)

        # Проверяем, что пользователь был добавлен в БД
        mock_uow_instance.user_dictionary.add_user.assert_called_once_with(123, "Test", "testuser")
        mock_uow_instance.commit.assert_called_once()

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


# --- Тесты для словаря (Dictionary Handlers) ---

@pytest.mark.asyncio
async def test_view_dictionary_page_handler_with_words():
    """Тест отображения страницы словаря, когда слова есть."""
    update = AsyncMock()
    update.callback_query.data = "dict:view:0"
    update.callback_query.from_user.id = 123
    context = MagicMock()

    # ИСПРАВЛЕНИЕ: убран префикс 'app.'
    with patch('handlers.dictionary.UnitOfWork') as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.user_dictionary.get_dictionary_page.return_value = [
            {'word_id': 1, 'hebrew': 'שלום', 'translation_text': 'привет'},
            {'word_id': 2, 'hebrew': 'כלב', 'translation_text': 'собака'},
        ]

        await view_dictionary_page_handler(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    call_text = update.callback_query.edit_message_text.call_args.args[0]
    assert "Ваш словарь (стр. 1):" in call_text
    assert "• שלום — привет" in call_text
    assert "• כלב — собака" in call_text


@pytest.mark.asyncio
async def test_view_dictionary_page_handler_empty():
    """Тест отображения словаря, когда он пуст."""
    update = AsyncMock()
    update.callback_query.data = "dict:view:0"
    update.callback_query.from_user.id = 123
    context = MagicMock()

    # ИСПРАВЛЕНИЕ: убран префикс 'app.'
    with patch('handlers.dictionary.UnitOfWork') as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.user_dictionary.get_dictionary_page.return_value = []

        await view_dictionary_page_handler(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "Ваш словарь пуст" in update.callback_query.edit_message_text.call_args.args[0]


@pytest.mark.asyncio
async def test_delete_word_flow():
    """Интеграционный тест полного цикла удаления слова."""
    update = AsyncMock()
    context = MagicMock()
    user_id = 123
    word_id_to_delete = 1
    page = 0
    update.callback_query.from_user.id = user_id

    # --- Шаг 1: Вход в режим удаления ---
    update.callback_query.data = f"dict:delete_mode:{page}"
    # ИСПРАВЛЕНИЕ: убран префикс 'app.'
    with patch('handlers.dictionary.UnitOfWork') as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.user_dictionary.get_dictionary_page.return_value = [
            {'word_id': word_id_to_delete, 'hebrew': 'שלום', 'translation_text': 'hello'}
        ]
        await view_dictionary_page_handler(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "Выберите слово для удаления" in update.callback_query.edit_message_text.call_args.args[0]
    update.callback_query.reset_mock()

    # --- Шаг 2: Выбор слова для удаления (открытие диалога подтверждения) ---
    update.callback_query.data = f"dict:confirm_delete:{word_id_to_delete}:{page}"
    # ИСПРАВЛЕНИЕ: убран префикс 'app.'
    with patch('handlers.dictionary.UnitOfWork') as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.words.get_word_hebrew_by_id.return_value = "שלום"
        await confirm_delete_word(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "Вы уверены, что хотите удалить слово 'שלום'" in update.callback_query.edit_message_text.call_args.args[0]
    update.callback_query.reset_mock()

    # --- Шаг 3: Подтверждение и фактическое удаление ---
    update.callback_query.data = f"dict:execute_delete:{word_id_to_delete}:{page}"
    # ИСПРАВЛЕНИЕ: убран префикс 'app.'
    with patch('handlers.dictionary.UnitOfWork') as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.user_dictionary.get_dictionary_page.return_value = []
        await execute_delete_word(update, context)

    mock_uow_instance.user_dictionary.remove_word_from_dictionary.assert_called_once_with(user_id, word_id_to_delete)
    mock_uow_instance.commit.assert_called_once()

    update.callback_query.edit_message_text.assert_called_once()
    assert "Ваш словарь пуст" in update.callback_query.edit_message_text.call_args.args[0]


# --- Тесты для поиска (Search Handlers) ---

@pytest.mark.asyncio
async def test_add_word_to_dictionary():
    update = AsyncMock()
    update.callback_query.data = "word:add:1"
    user_id = 123
    word_id = 1
    update.callback_query.from_user.id = user_id
    context = MagicMock()

    mock_word_data = CachedWord(
        word_id=word_id, hebrew='שלום', normalized_hebrew='שלום', is_verb=False,
        fetched_at=datetime.now(),
        translations=[
            Translation(
                translation_id=101, word_id=word_id, translation_text='hello',
                is_primary=True, context_comment=None
            )
        ],
        conjugations=[]
    )

    # ИСПРАВЛЕНИЕ: убран префикс 'app.'
    with patch('handlers.search.UnitOfWork') as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.words.get_word_by_id.return_value = mock_word_data

        # ИСПРАВЛЕНИЕ: убран префикс 'app.'
        with patch('handlers.search.display_word_card') as mock_display:
            await add_word_to_dictionary(update, context)

    mock_uow_instance.user_dictionary.add_word_to_dictionary.assert_called_once_with(user_id, word_id)
    mock_uow_instance.commit.assert_called_once()
    mock_display.assert_called_once()


@pytest.mark.asyncio
async def test_handle_text_message_word_not_in_db_found_externally():
    update = AsyncMock()
    update.message.text = "חדש"
    update.effective_user.id = 123
    context = MagicMock()
    context.bot.edit_message_text = AsyncMock()

    # ИСПРАВЛЕНИЕ: убран префикс 'app.'
    with patch('handlers.search.UnitOfWork') as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.words.find_word_by_normalized_form.return_value = None

        # ИСПРАВЛЕНИЕ: убран префикс 'app.'
        with patch('handlers.search.fetch_and_cache_word_data') as mock_fetch:
            mock_fetch.return_value = ('ok', {'word_id': 99, 'hebrew': 'חדש', 'translations': []})

            # ИСПРАВЛЕНИЕ: убран префикс 'app.'
            with patch('handlers.search.display_word_card') as mock_display:
                await handle_text_message(update, context)

    update.message.reply_text.assert_called_once_with("🔎 Ищу слово во внешнем словаре...")
    mock_fetch.assert_called_once()
    mock_display.assert_called_once()


# --- Тесты для тренировок (Training Handlers) ---

@pytest.mark.asyncio
async def test_start_flashcard_training_no_words():
    update = AsyncMock()
    update.callback_query = AsyncMock()
    update.callback_query.data = "train:he_ru"
    update.callback_query.from_user.id = 123
    context = MagicMock()

    # ИСПРАВЛЕНИЕ: убран префикс 'app.'
    with patch('handlers.training.UnitOfWork') as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.user_dictionary.get_user_words_for_training.return_value = []

        await start_flashcard_training(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "В словаре нет слов" in update.callback_query.edit_message_text.call_args.args[0]


@pytest.mark.asyncio
async def test_start_verb_trainer_no_verbs():
    update = AsyncMock()
    update.callback_query = AsyncMock()
    user_id = 123
    update.callback_query.from_user.id = user_id
    context = MagicMock()

    # ИСПРАВЛЕНИЕ: убран префикс 'app.'
    with patch('handlers.training.UnitOfWork') as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.words.get_random_verb_for_training.return_value = None

        await start_verb_trainer(update, context)

    mock_uow_instance.words.get_random_verb_for_training.assert_called_with(user_id)
    update.callback_query.edit_message_text.assert_called_once()
    assert "В вашем словаре нет глаголов для тренировки" in update.callback_query.edit_message_text.call_args.args[0]