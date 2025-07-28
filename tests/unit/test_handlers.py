import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

# Эти импорты верны, так как они отражают структуру вашего проекта
from dal.models import CachedWord, Translation
from handlers.common import start, main_menu
from handlers.dictionary import (
    view_dictionary_page_handler,
    confirm_delete_word,
    execute_delete_word,
)
from handlers.search import (
    handle_text_message,
    add_word_to_dictionary,
    show_verb_conjugations,
    pealim_search_handler,
    select_word_handler,
    search_in_pealim,
)

from handlers.training import (
    training_menu,
    start_flashcard_training,
    show_next_card,
    handle_self_evaluation,
    start_verb_trainer,
    end_training,
    check_verb_answer,
)
from config import CB_EVAL_CORRECT, CB_EVAL_INCORRECT, VERB_TRAINER_RETRY_ATTEMPTS, CB_SEARCH_PEALIM, CB_SELECT_WORD 


# --- Тесты для общих обработчиков (не требуют патчинга БД) ---


@pytest.mark.asyncio
async def test_start():
    update = AsyncMock()
    update.effective_user.first_name = "Test"
    update.effective_user.id = 123
    update.effective_user.username = "testuser"
    context = MagicMock()

    # ИСПРАВЛЕНИЕ: убран префикс 'app.'
    with patch("handlers.common.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value

        await start(update, context)

        # Проверяем, что пользователь был добавлен в БД
        mock_uow_instance.user_dictionary.add_user.assert_called_once_with(
            123, "Test", "testuser"
        )
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
    with patch("handlers.dictionary.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.user_dictionary.get_dictionary_page.return_value = [
            CachedWord(
                word_id=1,
                hebrew="שלום",
                normalized_hebrew="שלום",
                is_verb=False,
                fetched_at=datetime.now(),
                translations=[
                    Translation(
                        translation_id=1,
                        word_id=1,
                        translation_text="привет",
                        is_primary=True,
                    )
                ],
            ),
            CachedWord(
                word_id=2,
                hebrew="כלב",
                normalized_hebrew="כלב",
                is_verb=False,
                fetched_at=datetime.now(),
                translations=[
                    Translation(
                        translation_id=2,
                        word_id=2,
                        translation_text="собака",
                        is_primary=True,
                    )
                ],
            ),
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
    with patch("handlers.dictionary.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.user_dictionary.get_dictionary_page.return_value = []

        await view_dictionary_page_handler(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert (
        "Ваш словарь пуст" in update.callback_query.edit_message_text.call_args.args[0]
    )


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
    with patch("handlers.dictionary.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.user_dictionary.get_dictionary_page.return_value = [
            CachedWord(
                word_id=word_id_to_delete,
                hebrew="שלום",
                normalized_hebrew="שלום",
                is_verb=False,
                fetched_at=datetime.now(),
                translations=[
                    Translation(
                        translation_id=1,
                        word_id=word_id_to_delete,
                        translation_text="hello",
                        is_primary=True,
                    )
                ],
            )
        ]
        await view_dictionary_page_handler(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert (
        "Выберите слово для удаления"
        in update.callback_query.edit_message_text.call_args.args[0]
    )
    update.callback_query.reset_mock()

    # --- Шаг 2: Выбор слова для удаления (открытие диалога подтверждения) ---
    update.callback_query.data = f"dict:confirm_delete:{word_id_to_delete}:{page}"
    # ИСПРАВЛЕНИЕ: убран префикс 'app.'
    with patch("handlers.dictionary.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.words.get_word_hebrew_by_id.return_value = "שלום"
        await confirm_delete_word(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert (
        "Вы уверены, что хотите удалить слово 'שלום'"
        in update.callback_query.edit_message_text.call_args.args[0]
    )
    update.callback_query.reset_mock()

    # --- Шаг 3: Подтверждение и фактическое удаление ---
    update.callback_query.data = f"dict:execute_delete:{word_id_to_delete}:{page}"
    # ИСПРАВЛЕНИЕ: убран префикс 'app.'
    with patch("handlers.dictionary.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.user_dictionary.get_dictionary_page.return_value = []
        await execute_delete_word(update, context)

    mock_uow_instance.user_dictionary.remove_word_from_dictionary.assert_called_once_with(
        user_id, word_id_to_delete
    )
    mock_uow_instance.commit.assert_called_once()

    update.callback_query.edit_message_text.assert_called_once()
    assert (
        "Ваш словарь пуст" in update.callback_query.edit_message_text.call_args.args[0]
    )


# --- Тесты для поиска (Search Handlers) ---


@pytest.mark.asyncio
async def test_handle_text_message_no_local_match():
    """Тест: слово НЕ найдено в локальной БД, запускается внешний поиск."""
    update = AsyncMock()
    update.message.text = "חדש"
    context = MagicMock()

    with patch("handlers.search.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        # Новый метод возвращает ПУСТОЙ СПИСОК
        mock_uow_instance.words.find_words_by_normalized_form.return_value = []

        # Мокаем нашу новую функцию-хелпер
        with patch("handlers.search.search_in_pealim", new_callable=AsyncMock) as mock_search_pealim:
            await handle_text_message(update, context)

            # Проверяем, что поиск в БД был выполнен
            mock_uow_instance.words.find_words_by_normalized_form.assert_called_once_with("חדש")
            # Проверяем, что был вызван внешний поиск
            mock_search_pealim.assert_called_once()

@pytest.mark.asyncio
async def test_handle_text_message_one_local_match():
    """Тест: слово найдено в локальной БД (одно совпадение)."""
    update = AsyncMock()
    update.message.text = "שלום"
    update.effective_user.id = 123
    context = MagicMock()

    mock_word = MagicMock()
    mock_word.model_dump.return_value = {"word_id": 1, "hebrew": "שלום"}

    with patch("handlers.search.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        # Новый метод возвращает СПИСОК С ОДНИМ ЭЛЕМЕНТОМ
        mock_uow_instance.words.find_words_by_normalized_form.return_value = [mock_word]

        with patch("handlers.search.display_word_card", new_callable=AsyncMock) as mock_display:
            await handle_text_message(update, context)

            mock_display.assert_called_once()
            # Проверяем, что карточка вызвана с параметром для отображения кнопки "Искать еще"
            call_kwargs = mock_display.call_args.kwargs
            assert call_kwargs['show_pealim_search_button'] is True
            assert call_kwargs['search_query'] == "שלום"

@pytest.mark.asyncio
async def test_handle_text_message_multiple_local_matches():
    """Тест: слово найдено в локальной БД (несколько совпадений)."""
    update = AsyncMock()
    update.message.text = "חלב"
    context = MagicMock()

    # Мокаем два разных слова-омонима
    mock_word1 = MagicMock(word_id=10, hebrew="חָלָב", translations=[MagicMock(translation_text="молоко", is_primary=True)])
    mock_word2 = MagicMock(word_id=11, hebrew="לַחְלוֹב", translations=[MagicMock(translation_text="доить", is_primary=True)])

    with patch("handlers.search.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        # Новый метод возвращает СПИСОК С ДВУМЯ ЭЛЕМЕНТАМИ
        mock_uow_instance.words.find_words_by_normalized_form.return_value = [mock_word1, mock_word2]

        await handle_text_message(update, context)

        update.message.reply_text.assert_called_once()
        # Проверяем текст сообщения
        call_args, call_kwargs = update.message.reply_text.call_args
        assert "Найдено несколько вариантов" in call_args[0]

        # Проверяем кнопки
        keyboard = call_kwargs['reply_markup'].inline_keyboard
        assert len(keyboard) == 3 # Две кнопки для слов + одна для поиска
        assert "молоко" in keyboard[0][0].text
        assert f"{CB_SELECT_WORD}:10:חלב" in keyboard[0][0].callback_data
        assert "доить" in keyboard[1][0].text
        assert f"{CB_SELECT_WORD}:11:חלב" in keyboard[1][0].callback_data
        assert "Искать еще в Pealim" in keyboard[2][0].text
        assert f"{CB_SEARCH_PEALIM}:חלב" in keyboard[2][0].callback_data

# --- НОВЫЕ ТЕСТЫ ДЛЯ НОВЫХ ОБРАБОТЧИКОВ ---

@pytest.mark.asyncio
async def test_pealim_search_handler():
    """Тест: обработчик кнопки 'Искать еще в Pealim'."""
    update = AsyncMock()
    update.callback_query.data = f"{CB_SEARCH_PEALIM}:שלום"
    context = MagicMock()

    with patch("handlers.search.search_in_pealim", new_callable=AsyncMock) as mock_search_pealim:
        await pealim_search_handler(update, context)
        # Проверяем, что был вызван внешний поиск с правильным запросом
        mock_search_pealim.assert_called_once_with(update, context, "שלום")
        


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, data_list, expected_message",
    [
        ("not_found", [], "Слово 'מילה' не найдено."),
        (
            "error",
            [],
            "Внешний сервис словаря временно недоступен. Попробуйте, пожалуйста, позже.",
        ),
        (
            "db_error",
            [],
            "Произошла внутренняя ошибка при сохранении слова. Пожалуйста, попробуйте позже.",
        ),
    ],
)
async def test_search_in_pealim_failures(status, data_list, expected_message):
    """Тест: корректная обработка ошибок от парсера внутри search_in_pealim."""
    update = AsyncMock()
    context = AsyncMock()

    # Эмулируем вызов от callback_query
    update.message = None
    update.callback_query = AsyncMock()
    update.callback_query.message.message_id = 54321
    
    # Создаем мок для chat объекта
    mock_chat = MagicMock()
    mock_chat.id = 12345
    update.effective_chat = mock_chat
    update.callback_query.message.chat = mock_chat

    with patch(
        "handlers.search.fetch_and_cache_word_data", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = (status, data_list)

        await search_in_pealim(update, context, "מילה")

    # Проверяем, что бот сначала отредактировал сообщение на "Ищу..."
    assert "🔎 Ищу слово" in context.bot.edit_message_text.call_args_list[0].kwargs['text']

    # --- КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ ---
    # Получаем второй (последний) вызов edit_message_text
    final_call = context.bot.edit_message_text.call_args
    
    # Проверяем позиционный аргумент (args[0]), а не именованный (kwargs['text'])
    assert final_call.args[0] == expected_message
    
    # Проверяем остальные параметры
    assert final_call.kwargs['chat_id'] == 12345
    assert final_call.kwargs['message_id'] == 54321

    # Убедимся, что было ровно два вызова (первый - "Ищу...", второй - ошибка)
    assert context.bot.edit_message_text.call_count == 2

@pytest.mark.asyncio
async def test_select_word_handler():
    """Тест: обработчик выбора слова из списка."""
    update = AsyncMock()
    update.callback_query.data = f"{CB_SELECT_WORD}:10:חלב" # Выбираем слово с ID 10
    update.callback_query.from_user.id = 123
    context = MagicMock()
    
    mock_word_data = MagicMock()
    mock_word_data.model_dump.return_value = {"word_id": 10, "hebrew": "חָלָב"}

    with patch("handlers.search.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.words.get_word_by_id.return_value = mock_word_data

        with patch("handlers.search.display_word_card", new_callable=AsyncMock) as mock_display:
            await select_word_handler(update, context)

            # Проверяем, что запросили из БД слово с правильным ID
            mock_uow_instance.words.get_word_by_id.assert_called_once_with(10)
            
            # Проверяем, что была вызвана карточка
            mock_display.assert_called_once()
            call_kwargs = mock_display.call_args.kwargs
            # И что у нее тоже есть кнопка для повторного поиска
            assert call_kwargs['show_pealim_search_button'] is True
            assert call_kwargs['search_query'] == "חלב"


# --- Тесты для тренировок (Training Handlers) ---


@pytest.mark.asyncio
async def test_start_flashcard_training_no_words():
    update = AsyncMock()
    update.callback_query = AsyncMock()
    update.callback_query.data = "train:he_ru"
    update.callback_query.from_user.id = 123
    context = MagicMock()

    # ИСПРАВЛЕНИЕ: убран префикс 'app.'
    with patch("handlers.training.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.user_dictionary.get_user_words_for_training.return_value = []

        await start_flashcard_training(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert (
        "В словаре нет слов"
        in update.callback_query.edit_message_text.call_args.args[0]
    )


@pytest.mark.asyncio
async def test_start_verb_trainer_no_verbs():
    update = AsyncMock()
    update.callback_query = AsyncMock()
    user_id = 123
    update.callback_query.from_user.id = user_id
    context = MagicMock()

    # ИСПРАВЛЕНИЕ: убран префикс 'app.'
    with patch("handlers.training.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.words.get_random_verb_for_training.return_value = None

        await start_verb_trainer(update, context)

    mock_uow_instance.words.get_random_verb_for_training.assert_called_with(user_id)
    update.callback_query.edit_message_text.assert_called_once()
    assert (
        "В вашем словаре нет глаголов для тренировки"
        in update.callback_query.edit_message_text.call_args.args[0]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text_input, error_message",
    [
        ("word", "Пожалуйста, используйте только буквы иврита, пробелы и дефисы."),
        ("שלום לך", "Пожалуйста, отправляйте только по одному слову за раз."),
    ],
)
async def test_handle_text_message_invalid_input(text_input, error_message):
    """Тест: обработка невалидного ввода (не-иврит, несколько слов)."""
    update = AsyncMock()
    update.message.text = text_input
    context = MagicMock()

    await handle_text_message(update, context)

    update.message.reply_text.assert_called_once_with(error_message)


@pytest.mark.asyncio
async def test_handle_text_message_word_in_db():
    """Тест: слово найдено в локальной базе данных."""
    update = AsyncMock()
    update.message.text = "שלום"
    update.effective_user.id = 123
    context = MagicMock()

    mock_word_data = MagicMock()
    mock_word_data.model_dump.return_value = {"word_id": 1, "hebrew": "שלום"}

    with patch("handlers.search.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.words.find_words_by_normalized_form.return_value = (
            [mock_word_data]
        )

        with patch("handlers.search.display_word_card") as mock_display:
            await handle_text_message(update, context)

            mock_uow_instance.words.find_words_by_normalized_form.assert_called_once_with(
                "שלום"
            )
            mock_display.assert_called_once()

@pytest.mark.asyncio
async def test_handle_text_message_no_local_match_triggers_pealim_search():
    """Тест: если слово не найдено локально, вызывается search_in_pealim."""
    update = AsyncMock()
    update.message.text = "חדש"
    context = MagicMock()

    with patch("handlers.search.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        # 1. Новый метод возвращает пустой список
        mock_uow_instance.words.find_words_by_normalized_form.return_value = []

        # 2. Мокаем хелпер, а не сам fetch_and_cache
        with patch("handlers.search.search_in_pealim", new_callable=AsyncMock) as mock_search_helper:
            await handle_text_message(update, context)
            
            # 3. Проверяем, что хелпер был вызван
            mock_search_helper.assert_called_once_with(update, context, "חדש")


@pytest.mark.asyncio
async def test_show_verb_conjugations_success():
    """Тест: успешное отображение спряжений глагола."""
    update = AsyncMock()
    update.callback_query.data = "verb:show:1"
    context = MagicMock()
    word_id = 1

    mock_conjugations = [
        MagicMock(
            tense="PAST",
            person="1st singular",
            hebrew_form="אני הייתי",
            transcription="ani hayiti",
        )
    ]

    with patch("handlers.search.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.words.get_word_hebrew_by_id.return_value = "להיות"
        mock_uow_instance.words.get_conjugations_for_word.return_value = (
            mock_conjugations
        )

        await show_verb_conjugations(update, context)

        mock_uow_instance.words.get_conjugations_for_word.assert_called_once_with(
            word_id
        )
        update.callback_query.answer.assert_called_once()
        update.callback_query.edit_message_text.assert_called_once()

        call_args, call_kwargs = update.callback_query.edit_message_text.call_args
        assert "Спряжения для *להיות*" in call_args[0]
        assert "*Past*:" in call_args[0]
        assert "_1st singular_: אני הייתי (ani hayiti)" in call_args[0]


@pytest.mark.asyncio
async def test_show_verb_conjugations_not_found():
    """Тест: спряжения для глагола не найдены."""
    update = AsyncMock()
    update.callback_query.data = "verb:show:2"
    context = MagicMock()

    with patch("handlers.search.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.words.get_conjugations_for_word.return_value = []

        await show_verb_conjugations(update, context)

        update.callback_query.edit_message_text.assert_called_once()
        assert (
            "Для этого глагола нет таблицы спряжений"
            in update.callback_query.edit_message_text.call_args.args[0]
        )


@pytest.mark.asyncio
async def test_start_flashcard_training_with_words():
    """Тест: успешное начало тренировки, когда есть слова."""
    update = AsyncMock()
    update.callback_query.data = "train:he_ru"
    update.callback_query.from_user.id = 123
    context = MagicMock()
    context.user_data = {}

    mock_words = [
        CachedWord(
            word_id=1,
            hebrew="שלום",
            normalized_hebrew="שלום",
            is_verb=False,
            fetched_at=datetime.now(),
            translations=[
                Translation(
                    translation_id=1,
                    word_id=1,
                    translation_text="привет",
                    is_primary=True,
                )
            ],
        )
    ]

    with patch("handlers.training.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.user_dictionary.get_user_words_for_training.return_value = (
            mock_words
        )

        # Мокаем show_next_card, так как это отдельная функция в цепочке
        with patch(
            "handlers.training.show_next_card", new_callable=AsyncMock
        ) as mock_show_next:
            await start_flashcard_training(update, context)

            assert context.user_data["words"][0].hebrew == mock_words[0].hebrew
            assert context.user_data["training_mode"] == "train:he_ru"
            mock_show_next.assert_called_once()


@pytest.mark.asyncio
async def test_show_next_card_ends_training():
    """Тест: завершение тренировки, когда слова закончились."""
    update = AsyncMock()
    context = MagicMock()
    context.user_data = {
        "words": [],
        "idx": 0,
        "correct": 0,
        "training_mode": "train:he_ru",
    }

    await show_next_card(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert (
        "Тренировка окончена!"
        in update.callback_query.edit_message_text.call_args.args[0]
    )
    assert context.user_data == {}  # Проверяем, что данные были очищены


@pytest.mark.asyncio
# CORRECTED: Use the imported constants instead of hardcoded strings
@pytest.mark.parametrize(
    "evaluation, expected_srs", [(CB_EVAL_CORRECT, 1), (CB_EVAL_INCORRECT, 0)]
)
async def test_handle_self_evaluation_logic(evaluation, expected_srs):
    """Тест: обработка самооценки (правильно/неправильно) и обновление SRS."""
    update = AsyncMock()
    update.callback_query.data = evaluation  # Now uses the constant
    update.callback_query.from_user.id = 123
    context = MagicMock()
    context.user_data = {"words": [MagicMock(word_id=1)], "idx": 0, "correct": 0}

    with patch("handlers.training.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        # The current SRS level is 0 before the evaluation
        mock_uow_instance.user_dictionary.get_srs_level.return_value = 0

        with patch("handlers.training.show_next_card", new_callable=AsyncMock):
            await handle_self_evaluation(update, context)

            mock_uow_instance.user_dictionary.update_srs_level.assert_called_once()
            # This assertion will now pass because the correct logic path is triggered
            call_args, _ = mock_uow_instance.user_dictionary.update_srs_level.call_args
            assert call_args[0] == expected_srs
            mock_uow_instance.commit.assert_called_once()


@pytest.mark.asyncio
async def test_check_verb_answer_correct_and_incorrect():
    """Тест: проверка правильного и неправильного ответа в тренажере глаголов."""
    # 1. Случай с правильным ответом
    update_correct = AsyncMock()
    update_correct.message.text = "ילך"
    update_correct.effective_user.id = 123
    context_correct = MagicMock()
    context_correct.user_data = {
        "answer": MagicMock(hebrew_form="ילך", transcription="yelekh", word_id=5)
    }

    with patch("handlers.training.UnitOfWork"):
        await check_verb_answer(update_correct, context_correct)

    update_correct.message.reply_text.assert_called_once()
    assert "✅ Верно!" in update_correct.message.reply_text.call_args.args[0]

    # 2. Случай с неправильным ответом
    update_incorrect = AsyncMock()
    update_incorrect.message.text = "הולך"
    update_incorrect.effective_user.id = 123
    context_incorrect = MagicMock()
    context_incorrect.user_data = {
        "answer": MagicMock(hebrew_form="ילך", transcription="yelekh", word_id=5)
    }

    with patch("handlers.training.UnitOfWork"):
        await check_verb_answer(update_incorrect, context_incorrect)

    update_incorrect.message.reply_text.assert_called_once()
    assert "❌ Ошибка." in update_incorrect.message.reply_text.call_args.args[0]


@pytest.mark.asyncio
async def test_end_training():
    """Тест: принудительное завершение тренировки."""
    update = AsyncMock()
    context = MagicMock()

    await end_training(update, context)

    update.callback_query.answer.assert_called_once()
    update.callback_query.answer.assert_called_once()
    update.callback_query.edit_message_text.assert_called_once()
    assert (
        "Тренировка прервана"
        in update.callback_query.edit_message_text.call_args.kwargs["text"]
    )


@pytest.mark.asyncio
async def test_training_menu_as_command():
    """Тест: вызов меню тренировок как новой команды, а не колбэка."""
    update = AsyncMock()
    # Эмулируем вызов не через кнопку (query is None)
    update.callback_query = None
    update.effective_chat.id = 12345
    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await training_menu(update, context)

    # Проверяем, что было отправлено новое сообщение, а не отредактировано существующее
    context.bot.send_message.assert_called_once()
    assert (
        "Выберите режим тренировки" in context.bot.send_message.call_args.kwargs["text"]
    )


@pytest.mark.asyncio
async def test_start_verb_trainer_happy_path():
    """Тест: успешное начало тренировки глаголов с первой попытки."""
    update = AsyncMock()
    update.callback_query.from_user.id = 123
    context = MagicMock()
    context.user_data = {}

    mock_verb = MagicMock(word_id=10, hebrew="לכתוב")
    mock_conjugation = MagicMock(
        tense="FUTURE",
        person="1st plural",
        hebrew_form="נכתוב",
    )

    with patch("handlers.training.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.words.get_random_verb_for_training.return_value = mock_verb
        mock_uow_instance.words.get_random_conjugation_for_word.return_value = (
            mock_conjugation
        )

        await start_verb_trainer(update, context)

        # Проверяем, что правильные данные сохранились
        assert context.user_data["answer"] == mock_conjugation

        # Проверяем, что пользователю задан правильный вопрос
        update.callback_query.edit_message_text.assert_called_once()

        # ИСПРАВЛЕНО: Обращаемся к позиционному аргументу args[0]
        call_text = update.callback_query.edit_message_text.call_args.args[0]
        assert "Глагол: *לכתוב*" in call_text
        assert "Напишите его форму для:\n*FUTURE, 1st plural*" in call_text


@pytest.mark.asyncio
async def test_start_verb_trainer_retry_logic():
    """Тест: тренажер глаголов находит спряжение со второй попытки."""
    update = AsyncMock()
    update.callback_query.from_user.id = 123
    context = MagicMock()
    context.user_data = {}

    mock_verb_no_conj = MagicMock(word_id=11, hebrew="פועל_בלי_כלום")
    mock_verb_with_conj = MagicMock(word_id=12, hebrew="לרוץ")
    mock_conjugation = MagicMock(
        tense="PRESENT",
        person="m. plural",
        hebrew_form="רצים",
    )

    with patch("handlers.training.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        # Первый вызов возвращает глагол без спряжений, второй - с ними
        mock_uow_instance.words.get_random_verb_for_training.side_effect = [
            mock_verb_no_conj,
            mock_verb_with_conj,
        ]
        # Первый вызов не находит спряжений, второй - находит
        mock_uow_instance.words.get_random_conjugation_for_word.side_effect = [
            None,
            mock_conjugation,
        ]

        await start_verb_trainer(update, context)

        # Проверяем, что мы дважды пытались найти глагол
        assert mock_uow_instance.words.get_random_verb_for_training.call_count == 2
        # И дважды пытались найти спряжение
        assert mock_uow_instance.words.get_random_conjugation_for_word.call_count == 2

        # Проверяем, что в итоге пользователю показали второй, "удачный" глагол
        update.callback_query.edit_message_text.assert_called_once()

        # ИСПРАВЛЕНО: Обращаемся к позиционному аргументу args[0]
        call_text = update.callback_query.edit_message_text.call_args.args[0]
        assert "Глагол: *לרוץ*" in call_text
        assert "PRESENT, m. plural" in call_text


@pytest.mark.asyncio
async def test_start_verb_trainer_fails_after_retries():
    """Тест: тренажер глаголов не находит спряжений после всех попыток."""
    update = AsyncMock()
    update.callback_query.from_user.id = 123
    context = MagicMock()

    mock_verb = MagicMock(word_id=11, hebrew="פועל_בלי_כלום")

    with patch("handlers.training.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        # Всегда возвращаем один и тот же глагол
        mock_uow_instance.words.get_random_verb_for_training.return_value = mock_verb
        # Но для него никогда не находится спряжений
        mock_uow_instance.words.get_random_conjugation_for_word.return_value = None

        await start_verb_trainer(update, context)

        # Проверяем, что было сделано ровно VERB_TRAINER_RETRY_ATTEMPTS попыток
        assert (
            mock_uow_instance.words.get_random_verb_for_training.call_count
            == VERB_TRAINER_RETRY_ATTEMPTS
        )

        # Проверяем, что было отправлено сообщение об ошибке
        update.callback_query.edit_message_text.assert_called_once()

        # CORRECTED: Access the first positional argument instead of a keyword argument
        call_text = update.callback_query.edit_message_text.call_args.args[0]
        assert "Не удалось найти подходящий глагол для тренировки" in call_text


@pytest.mark.asyncio
async def test_check_verb_answer_no_context():
    """Тест: проверка ответа глагола при пустом user_data (защита от ошибок)."""
    update = AsyncMock()
    context = MagicMock()
    # `answer` отсутствует в user_data
    context.user_data = {}

    # Мокаем training_menu, чтобы проверить, что произошел выход в него
    with patch("handlers.training.training_menu", new_callable=AsyncMock) as mock_menu:
        await check_verb_answer(update, context)
        mock_menu.assert_called_once()
