import pytest
from unittest.mock import AsyncMock, Mock, patch

from handlers.search import add_word_to_dictionary
from handlers.dictionary import execute_delete_word, view_dictionary_page_handler
from dal.unit_of_work import UnitOfWork
from config import CB_DICT_VIEW, CB_DICT_EXECUTE_DELETE, DICT_WORDS_PER_PAGE

# Импортируем модели для создания тестовых данных
from dal.models import CreateCachedWord, CreateTranslation, PartOfSpeech


@pytest.mark.asyncio
async def test_add_word_to_dictionary(memory_db):
    """Тестирует добавление слова в словарь."""
    update = Mock()
    update.callback_query = AsyncMock()
    update.callback_query.from_user.id = 123
    # ID слова теперь 1, так как база данных для каждого теста чистая
    update.callback_query.data = "word:add:1"
    context = Mock()
    context.bot = AsyncMock()

    with UnitOfWork() as uow:
        # Используем новую модель для создания слова
        word_to_create = CreateCachedWord(
            hebrew="מילה",
            normalized_hebrew="מילה",
            transcription="mila",
            part_of_speech=PartOfSpeech.NOUN,
            translations=[CreateTranslation(translation_text="word", is_primary=True)],
        )
        uow.words.create_cached_word(word_to_create)
        uow.commit()

    with patch("handlers.search.display_word_card"):
        await add_word_to_dictionary(update, context)

    update.callback_query.answer.assert_called_once_with("Добавлено!")


@pytest.mark.asyncio
async def test_delete_word_from_dictionary(memory_db):
    """Тестирует удаление слова из словаря пользователя."""
    update = Mock()
    query = AsyncMock()
    update.callback_query = query
    query.from_user.id = 123

    with UnitOfWork() as uow:
        # Создаем слова с помощью новых моделей
        word_to_delete_model = CreateCachedWord(
            hebrew="למחוק",
            normalized_hebrew="למחוק",
            transcription="limkhok",
            part_of_speech=PartOfSpeech.VERB,
            translations=[
                CreateTranslation(translation_text="to delete", is_primary=True)
            ],
        )
        word_id_to_delete = uow.words.create_cached_word(word_to_delete_model)

        word_to_keep_model = CreateCachedWord(
            hebrew="לשמור",
            normalized_hebrew="לשמור",
            transcription="lishmor",
            part_of_speech=PartOfSpeech.VERB,
            translations=[
                CreateTranslation(translation_text="to keep", is_primary=True)
            ],
        )
        word_id_to_keep = uow.words.create_cached_word(word_to_keep_model)

        uow.user_dictionary.add_user(123, "Test", "testuser")
        uow.user_dictionary.add_word_to_dictionary(123, word_id_to_delete)
        uow.user_dictionary.add_word_to_dictionary(123, word_id_to_keep)
        uow.commit()

    query.data = f"{CB_DICT_EXECUTE_DELETE}:{word_id_to_delete}:0"

    with patch("handlers.dictionary.view_dictionary_page_logic") as mock_view_logic:
        await execute_delete_word(update, Mock())

    query.answer.assert_called_once_with("Слово удалено")
    mock_view_logic.assert_called_once()
    args, kwargs = mock_view_logic.call_args
    assert kwargs["page"] == 0
    assert kwargs["deletion_mode"] is False
    assert kwargs["exclude_word_id"] == word_id_to_delete

    with UnitOfWork() as uow:
        assert not uow.user_dictionary.is_word_in_dictionary(123, word_id_to_delete)
        assert uow.user_dictionary.is_word_in_dictionary(123, word_id_to_keep)


@pytest.mark.asyncio
async def test_view_dictionary_pagination(memory_db):
    """Test pagination of the user's dictionary."""
    update = Mock()
    query = AsyncMock()
    update.callback_query = query
    query.from_user.id = 123
    context = Mock()
    context.bot = AsyncMock()

    # Setup: Add more words than one page can hold
    with UnitOfWork() as uow:
        uow.user_dictionary.add_user(123, "Test", "testuser")
        for i in range(DICT_WORDS_PER_PAGE + 1):
            word_model = CreateCachedWord(
                hebrew=f"מילה{i}",
                normalized_hebrew=f"מילה{i}",
                transcription=f"mila{i}",
                part_of_speech=PartOfSpeech.NOUN,
                translations=[
                    CreateTranslation(translation_text=f"word{i}", is_primary=True)
                ],
            )
            word_id = uow.words.create_cached_word(word_model)
            uow.user_dictionary.add_word_to_dictionary(123, word_id)
        uow.commit()

    # Test Page 1
    query.data = f"{CB_DICT_VIEW}:0"
    await view_dictionary_page_handler(update, context)

    query.edit_message_text.assert_called_once()
    args, kwargs = query.edit_message_text.call_args

    # Check text content for page 1
    text_page_1 = args[0]
    assert "Ваш словарь (стр. 1):" in text_page_1
    for i in range(DICT_WORDS_PER_PAGE):
        assert f"מילה{i}" in text_page_1

    # Check buttons for page 1
    markup_page_1 = kwargs["reply_markup"]
    nav_buttons = markup_page_1.inline_keyboard[0]
    assert len(nav_buttons) == 1
    assert nav_buttons[0].text == "▶️"
    assert nav_buttons[0].callback_data == f"{CB_DICT_VIEW}:1"

    query.edit_message_text.reset_mock()

    # Test Page 2
    query.data = f"{CB_DICT_VIEW}:1"
    await view_dictionary_page_handler(update, context)

    query.edit_message_text.assert_called_once()
    args, kwargs = query.edit_message_text.call_args

    # Check text content for page 2
    text_page_2 = args[0]
    assert "Ваш словарь (стр. 2):" in text_page_2
    assert f"מילה{DICT_WORDS_PER_PAGE}" in text_page_2

    # Check buttons for page 2
    markup_page_2 = kwargs["reply_markup"]
    nav_buttons = markup_page_2.inline_keyboard[0]
    assert len(nav_buttons) == 1
    assert nav_buttons[0].text == "◀️"
    assert nav_buttons[0].callback_data == f"{CB_DICT_VIEW}:0"
