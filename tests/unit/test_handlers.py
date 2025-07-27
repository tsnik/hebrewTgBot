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

# ИСПРАВЛЕНИЕ: Добавлен импорт display_word_card для прямого тестирования
from handlers.common import display_word_card
from config import CB_EVAL_CORRECT, CB_EVAL_INCORRECT, VERB_TRAINER_RETRY_ATTEMPTS


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "word_data, in_dictionary, message_id, expected_text_parts, expected_buttons",
    [
        # --- Сценарий 1: Новое слово (не в словаре), отправка нового сообщения ---
        (
            {
                "word_id": 1,
                "hebrew": "חדש",
                "transcription": "chadash",
                "part_of_speech": "adjective",
                "translations": [{"translation_text": "new", "is_primary": True}],
                "masculine_singular": "חדש",
                "feminine_singular": "חדשה",
            },
            False,
            None,
            ["Найдено: *חדש*", "ж.р., ед.ч.: חדשה"],
            ["➕ Добавить", "⬅️ В главное меню"],
        ),
        # --- Сценарий 2: Слово уже в словаре, редактирование существующего сообщения ---
        (
            {
                "word_id": 2,
                "hebrew": "ישן",
                "transcription": "yashan",
                "part_of_speech": "noun",
                "translations": [{"translation_text": "old", "is_primary": True}],
                "gender": "masculine",
                "plural_form": "ישנים",
            },
            True,
            12345,
            ["Слово *ישן* уже в вашем словаре", "Род: Мужской род", "Мн. число: ישנים"],
            ["🗑️ Удалить", "⬅️ В главное меню"],
        ),
        # --- Сценарий 3: Глагол, проверка кнопки "Спряжения" ---
        (
            {
                "word_id": 3,
                "hebrew": "לכתוב",
                "transcription": "lichtov",
                "part_of_speech": "verb",
                "translations": [{"translation_text": "to write", "is_primary": True}],
                "root": "כ.ת.ב",
                "binyan": "pa'al",
            },
            False,
            None,
            ["Найдено: *לכתוב*", "\nКорень: כ.ת.ב", "\nБиньян: pa'al"],
            ["➕ Добавить", "📖 Спряжения", "⬅️ В главное меню"],
        ),
    ],
)
async def test_display_word_card(
    word_data, in_dictionary, message_id, expected_text_parts, expected_buttons
):
    """Тест: универсальная проверка отображения карточки слова."""
    context = AsyncMock()
    user_id = 123
    chat_id = 456

    # Мокаем UnitOfWork только для этой функции, чтобы не мешать другим тестам
    with patch("handlers.common.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.user_dictionary.is_word_in_dictionary.return_value = (
            in_dictionary
        )

        await display_word_card(
            context,
            user_id,
            chat_id,
            word_data,
            message_id,
            # Передаем in_dictionary=None, чтобы симулировать реальный вызов,
            # где этот параметр определяется внутри функции
            in_dictionary=None,
        )

    # Проверяем, был ли вызван правильный метод: edit или send
    if message_id:
        context.bot.edit_message_text.assert_called_once()
        context.bot.send_message.assert_not_called()
        call_kwargs = context.bot.edit_message_text.call_args.kwargs
    else:
        context.bot.send_message.assert_called_once()
        context.bot.edit_message_text.assert_not_called()
        call_kwargs = context.bot.send_message.call_args.kwargs

    # Проверяем содержимое текста сообщения
    sent_text = call_kwargs["text"]
    for part in expected_text_parts:
        assert part in sent_text

    # Проверяем кнопки
    sent_buttons = call_kwargs["reply_markup"].inline_keyboard
    # "Сплющиваем" массив кнопок в один список для удобства проверки
    sent_button_texts = [btn.text for row in sent_buttons for btn in row]
    assert sent_button_texts == expected_buttons


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
async def test_add_word_to_dictionary():
    update = AsyncMock()
    update.callback_query.data = "word:add:1"
    user_id = 123
    word_id = 1
    update.callback_query.from_user.id = user_id
    context = MagicMock()

    mock_word_data = CachedWord(
        word_id=word_id,
        hebrew="שלום",
        normalized_hebrew="שלום",
        is_verb=False,
        fetched_at=datetime.now(),
        translations=[
            Translation(
                translation_id=101,
                word_id=word_id,
                translation_text="hello",
                is_primary=True,
                context_comment=None,
            )
        ],
        conjugations=[],
    )

    # ИСПРАВЛЕНИЕ: убран префикс 'app.'
    with patch("handlers.search.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.words.get_word_by_id.return_value = mock_word_data

        # ИСПРАВЛЕНИЕ: убран префикс 'app.'
        with patch("handlers.search.display_word_card") as mock_display:
            await add_word_to_dictionary(update, context)

    mock_uow_instance.user_dictionary.add_word_to_dictionary.assert_called_once_with(
        user_id, word_id
    )
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
    with patch("handlers.search.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.words.find_word_by_normalized_form.return_value = None

        # ИСПРАВЛЕНИЕ: убран префикс 'app.'
        with patch("handlers.search.fetch_and_cache_word_data") as mock_fetch:
            mock_fetch.return_value = (
                "ok",
                {"word_id": 99, "hebrew": "חדש", "translations": []},
            )

            # ИСПРАВЛЕНИЕ: убран префикс 'app.'
            with patch("handlers.search.display_word_card") as mock_display:
                await handle_text_message(update, context)

    update.message.reply_text.assert_called_once_with(
        "🔎 Ищу слово во внешнем словаре..."
    )
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
        mock_uow_instance.words.find_word_by_normalized_form.return_value = (
            mock_word_data
        )

        with patch("handlers.search.display_word_card") as mock_display:
            await handle_text_message(update, context)

            mock_uow_instance.words.find_word_by_normalized_form.assert_called_once_with(
                "שלום"
            )
            mock_display.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, message",
    [
        ("not_found", "Слово 'מילה' не найдено."),
        (
            "error",
            "Внешний сервис словаря временно недоступен. Попробуйте, пожалуйста, позже.",
        ),
        (
            "db_error",
            "Произошла внутренняя ошибка при сохранении слова. Пожалуйста, попробуйте позже.",
        ),
    ],
)
async def test_handle_text_message_external_search_failures(status, message):
    """Тест: обработка различных ошибок от внешнего сервиса."""
    update = AsyncMock()
    update.message.text = "מילה"
    update.effective_chat.id = 12345
    context = AsyncMock()

    # Мокаем сообщение-статус, чтобы у него был message_id для редактирования
    status_message = AsyncMock()
    status_message.message_id = 54321
    update.message.reply_text.return_value = status_message

    with patch("handlers.search.UnitOfWork") as mock_uow_class:
        mock_uow_instance = mock_uow_class.return_value.__enter__.return_value
        mock_uow_instance.words.find_word_by_normalized_form.return_value = None

        with patch(
            "handlers.search.fetch_and_cache_word_data", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = (status, None)

            await handle_text_message(update, context)

            update.message.reply_text.assert_called_once_with(
                "🔎 Ищу слово во внешнем словаре..."
            )
            context.bot.edit_message_text.assert_called_once_with(
                message, chat_id=12345, message_id=54321
            )


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
