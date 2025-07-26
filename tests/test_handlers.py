import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from handlers.common import start, main_menu
from handlers.dictionary import view_dictionary_page_handler, confirm_delete_word, execute_delete_word
from handlers.search import handle_text_message, add_word_to_dictionary, show_verb_conjugations
from handlers.training import training_menu, start_flashcard_training, show_answer, handle_self_evaluation, start_verb_trainer
from services.parser import fetch_and_cache_word_data
from dal.unit_of_work import UnitOfWork

@pytest.mark.asyncio
async def test_start(memory_db_uow: UnitOfWork):
    update = AsyncMock()
    update.effective_user.id = 123
    update.effective_user.first_name = "Test"
    update.effective_user.username = "testuser"
    context = MagicMock()
    context.bot.send_message = AsyncMock()

    with patch('handlers.common.UnitOfWork', return_value=memory_db_uow):
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
async def test_view_dictionary_page_handler(memory_db_uow: UnitOfWork):
    update = AsyncMock()
    update.callback_query.data = "dict:view:0"
    update.callback_query.from_user.id = 123
    context = MagicMock()

    with patch('handlers.dictionary.UnitOfWork', return_value=memory_db_uow):
        await view_dictionary_page_handler(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "Ваш словарь пуст" in update.callback_query.edit_message_text.call_args.args[0]

@pytest.mark.asyncio
async def test_start_verb_trainer_no_conjugations(memory_db_uow: UnitOfWork):
    update = AsyncMock()
    update.callback_query = AsyncMock()
    update.callback_query.from_user.id = 123
    context = MagicMock()

    with patch('handlers.training.UnitOfWork', return_value=memory_db_uow):
        await start_verb_trainer(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "В вашем словаре нет глаголов для тренировки." in update.callback_query.edit_message_text.call_args.args[0]

@pytest.mark.asyncio
async def test_start_flashcard_training_no_words(memory_db_uow: UnitOfWork):
    update = AsyncMock()
    update.callback_query = AsyncMock()
    update.callback_query.data = "train:he_ru"
    update.callback_query.from_user.id = 123
    context = MagicMock()

    with patch('handlers.training.UnitOfWork', return_value=memory_db_uow):
        await start_flashcard_training(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "В словаре нет слов (существительных/прилагательных) для этой тренировки." in update.callback_query.edit_message_text.call_args.args[0]

@pytest.mark.asyncio
async def test_add_word_to_dictionary():
    update = AsyncMock()
    update.callback_query = AsyncMock()
    update.callback_query.data = "word:add:1"
    update.callback_query.from_user.id = 123
    context = MagicMock()

    with patch('handlers.search.UnitOfWork'):
        with patch('handlers.search.display_word_card') as mock_display:
            await add_word_to_dictionary(update, context)

    mock_display.assert_called_once()

@pytest.mark.asyncio
async def test_show_verb_conjugations(memory_db_uow: UnitOfWork):
    update = AsyncMock()
    update.callback_query = AsyncMock()
    update.callback_query.data = "verb:show:1"
    context = MagicMock()

    with patch('handlers.search.UnitOfWork', return_value=memory_db_uow):
        await show_verb_conjugations(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "Для этого глагола нет таблицы спряжений." in update.callback_query.edit_message_text.call_args.args[0]

@pytest.mark.asyncio
async def test_handle_text_message_word_in_db():
    update = AsyncMock()
    update.message.text = "שלום"
    update.effective_user.id = 123
    context = MagicMock()

    with patch('handlers.search.UnitOfWork'):
        with patch('handlers.search.display_word_card') as mock_display:
            await handle_text_message(update, context)

    mock_display.assert_called_once()

@pytest.mark.asyncio
async def test_handle_text_message_word_not_in_db():
    update = AsyncMock()
    update.message.text = "שלום"
    update.effective_user.id = 123
    context = MagicMock()
    context.bot.edit_message_text = AsyncMock()

    with patch('handlers.search.UnitOfWork'):
        with patch('services.parser.fetch_and_cache_word_data') as mock_fetch:
            mock_fetch.return_value = ('ok', {'hebrew': 'שלום', 'translations': [{'translation_text': 'hello'}]})
            with patch('handlers.search.display_word_card') as mock_display:
                await handle_text_message(update, context)

    update.message.reply_text.assert_called_once_with("🔎 Ищу слово во внешнем словаре...")
    mock_display.assert_called_once()

@pytest.mark.asyncio
async def test_training_flow():
    update = AsyncMock()
    update.callback_query = AsyncMock()
    update.callback_query.from_user.id = 123
    context = MagicMock()
    context.user_data = {}

    # 1. Start training
    with patch('handlers.training.UnitOfWork'):
        await training_menu(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "Выберите режим тренировки" in update.callback_query.edit_message_text.call_args.kwargs['text']
    update.callback_query.reset_mock()

    # 2. Select mode
    update.callback_query.data = "train:he_ru"
    with patch('handlers.training.UnitOfWork') as mock_uow:
        mock_uow.return_value.__enter__.return_value.user_dictionary.get_user_words_for_training.return_value = [
            {'word_id': 1, 'hebrew': 'שלום', 'translation_text': 'hello', 'srs_level': 0, 'transcription': 'shalom'}
        ]
        await start_flashcard_training(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "Слово 1/1" in update.callback_query.edit_message_text.call_args.kwargs['text']
    assert "שלום" in update.callback_query.edit_message_text.call_args.kwargs['text']
    update.callback_query.reset_mock()

    # 3. Show answer
    await show_answer(update, context)
    assert len(update.callback_query.edit_message_text.call_args_list) == 1
    assert "hello" in update.callback_query.edit_message_text.call_args_list[0].args[0]

    # 4. Evaluate
    update.callback_query.data = "train:eval_correct"
    with patch('handlers.training.UnitOfWork') as mock_uow:
        mock_uow.return_value.__enter__.return_value.user_dictionary.get_srs_level.return_value = {'srs_level': 0}
        await handle_self_evaluation(update, context)

@pytest.mark.asyncio
async def test_delete_word_flow():
    update = AsyncMock()
    update.callback_query = AsyncMock()
    update.callback_query.from_user.id = 123
    context = MagicMock()
    context.user_data = {}

    # 1. Enter deletion mode
    update.callback_query.data = "dict:delete_mode:0"
    with patch('handlers.dictionary.UnitOfWork') as mock_uow:
        mock_uow.return_value.__enter__.return_value.user_dictionary.get_dictionary_page.return_value = []
        await view_dictionary_page_handler(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "Ваш словарь пуст" in update.callback_query.edit_message_text.call_args.args[0]
    update.callback_query.reset_mock()

    # 2. Select word to delete
    update.callback_query.data = "dict:confirm_delete:1:0"
    with patch('handlers.dictionary.UnitOfWork') as mock_uow:
        mock_uow.return_value.__enter__.return_value.words.get_word_hebrew_by_id.return_value = "שלום"
        await confirm_delete_word(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "Вы уверены" in update.callback_query.edit_message_text.call_args.args[0]
    update.callback_query.reset_mock()

    # 3. Confirm deletion
    update.callback_query.data = "dict:execute_delete:1:0"
    with patch('handlers.dictionary.UnitOfWork') as mock_uow:
        mock_uow.return_value.__enter__.return_value.user_dictionary.get_dictionary_page.return_value = []
        await execute_delete_word(update, context)

    mock_uow.return_value.__enter__.return_value.user_dictionary.remove_word_from_dictionary.assert_called_once_with(update.callback_query.from_user.id, 1)
    update.callback_query.edit_message_text.assert_called_once()
    assert "Ваш словарь пуст" in update.callback_query.edit_message_text.call_args.args[0]
