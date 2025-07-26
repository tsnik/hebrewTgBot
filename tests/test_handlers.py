import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.handlers.common import start, main_menu
from app.handlers.dictionary import view_dictionary_page_handler, confirm_delete_word, execute_delete_word
from app.handlers.search import handle_text_message, add_word_to_dictionary, show_verb_conjugations
from app.handlers.training import training_menu, start_flashcard_training, show_answer, handle_self_evaluation, start_verb_trainer
from app.services.parser import fetch_and_cache_word_data

@pytest.mark.asyncio
async def test_start():
    update = AsyncMock()
    update.effective_user.first_name = "Test"
    context = MagicMock()
    context.bot.send_message = AsyncMock()

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
async def test_view_dictionary_page_handler():
    update = AsyncMock()
    update.callback_query.data = "dict:view:0"
    update.callback_query.from_user.id = 123
    context = MagicMock()

    with patch('app.handlers.dictionary.user_dict_repo') as mock_repo:
        mock_repo.get_dictionary_page.return_value = []
        await view_dictionary_page_handler(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "Ваш словарь пуст" in update.callback_query.edit_message_text.call_args.args[0]

@pytest.mark.asyncio
async def test_start_verb_trainer_no_conjugations():
    update = AsyncMock()
    update.callback_query = AsyncMock()
    context = MagicMock()

    with patch('app.handlers.training.db_read_query') as mock_read:
        # Simulate finding a verb, but no conjugations
        mock_read.side_effect = [
            {'word_id': 1, 'hebrew': 'глагол'}, None,
            {'word_id': 1, 'hebrew': 'глагол'}, None,
            {'word_id': 1, 'hebrew': 'глагол'}, None,
        ]
        await start_verb_trainer(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "Не удалось найти подходящий глагол" in update.callback_query.edit_message_text.call_args.args[0]

@pytest.mark.asyncio
async def test_start_flashcard_training_no_words():
    update = AsyncMock()
    update.callback_query = AsyncMock()
    update.callback_query.data = "train:he_ru"
    context = MagicMock()

    with patch('app.handlers.training.db_read_query') as mock_read:
        mock_read.return_value = []
        await start_flashcard_training(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "В словаре нет слов" in update.callback_query.edit_message_text.call_args.args[0]

@pytest.mark.asyncio
async def test_add_word_to_dictionary():
    update = AsyncMock()
    update.callback_query = AsyncMock()
    update.callback_query.data = "word:add:1"
    context = MagicMock()

    with patch('app.handlers.search.user_dict_repo') as mock_user_dict_repo:
        with patch('app.handlers.search.word_repo') as mock_word_repo:
            mock_word_repo.get_word_by_id.return_value = MagicMock(
                dict=MagicMock(return_value={'word_id': 1, 'hebrew': 'שלום', 'translations': [{'translation_text': 'hello'}]})
            )
            with patch('app.handlers.search.display_word_card') as mock_display:
                await add_word_to_dictionary(update, context)

    mock_user_dict_repo.add_word_to_dictionary.assert_called_once_with(update.callback_query.from_user.id, 1)
    mock_display.assert_called_once()

@pytest.mark.asyncio
async def test_show_verb_conjugations():
    update = AsyncMock()
    update.callback_query = AsyncMock()
    update.callback_query.data = "verb:show:1"
    context = MagicMock()

    with patch('app.handlers.search.word_repo') as mock_word_repo:
        mock_word_repo.get_word_hebrew_by_id.return_value = "לִכְתּוֹב"
        mock_word_repo.get_conjugations_for_word.return_value = [
            MagicMock(tense='present', person='m.s.', hebrew_form='כּוֹתֵב', transcription='kotev')
        ]
        await show_verb_conjugations(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "Спряжения для" in update.callback_query.edit_message_text.call_args.args[0]
    assert "כּוֹתֵב" in update.callback_query.edit_message_text.call_args.args[0]

@pytest.mark.asyncio
async def test_handle_text_message_word_in_db():
    update = AsyncMock()
    update.message.text = "שלום"
    context = MagicMock()

    with patch('app.handlers.search.word_repo') as mock_repo:
        mock_repo.find_word_by_normalized_form.return_value = MagicMock(
            dict=MagicMock(return_value={'hebrew': 'שלום', 'translations': [{'translation_text': 'hello'}]})
        )
        with patch('app.handlers.search.display_word_card') as mock_display:
            await handle_text_message(update, context)

    mock_display.assert_called_once()

@pytest.mark.asyncio
async def test_handle_text_message_word_not_in_db():
    update = AsyncMock()
    update.message.text = "שלום"
    context = MagicMock()
    context.bot.edit_message_text = AsyncMock()

    with patch('app.handlers.search.word_repo') as mock_repo:
        mock_repo.find_word_by_normalized_form.return_value = None
        with patch('app.handlers.search.fetch_and_cache_word_data') as mock_fetch:
            mock_fetch.return_value = ('ok', {'hebrew': 'שלום', 'translations': [{'translation_text': 'hello'}]})
            with patch('app.handlers.search.display_word_card') as mock_display:
                await handle_text_message(update, context)

    update.message.reply_text.assert_called_once_with("🔎 Ищу слово во внешнем словаре...")
    mock_display.assert_called_once()

@pytest.mark.asyncio
async def test_training_flow():
    update = AsyncMock()
    update.callback_query = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    # 1. Start training
    with patch('app.handlers.training.db_read_query') as mock_read:
        mock_read.return_value = [
            {'word_id': 1, 'hebrew': 'שלום', 'translation_text': 'hello', 'srs_level': 0, 'transcription': 'shalom'}
        ]
        await training_menu(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "Выберите режим тренировки" in update.callback_query.edit_message_text.call_args.kwargs['text']
    update.callback_query.reset_mock()

    # 2. Select mode
    update.callback_query.data = "train:he_ru"
    with patch('app.handlers.training.db_read_query') as mock_read:
        mock_read.return_value = [
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
    with patch('app.handlers.training.db_write_query') as mock_write:
        with patch('app.handlers.training.db_read_query') as mock_read:
            mock_read.return_value = {'srs_level': 0}
            await handle_self_evaluation(update, context)

    mock_write.assert_called_once()

@pytest.mark.asyncio
async def test_delete_word_flow():
    update = AsyncMock()
    update.callback_query = AsyncMock()
    context = MagicMock()
    context.user_data = {}

    # 1. Enter deletion mode
    update.callback_query.data = "dict:delete_mode:0"
    with patch('app.handlers.dictionary.user_dict_repo') as mock_repo:
        mock_repo.get_dictionary_page.return_value = [
            {'word_id': 1, 'hebrew': 'שלום', 'translation_text': 'hello'}
        ]
        await view_dictionary_page_handler(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "Выберите слово для удаления" in update.callback_query.edit_message_text.call_args.args[0]
    update.callback_query.reset_mock()

    # 2. Select word to delete
    update.callback_query.data = "dict:confirm_delete:1:0"
    with patch('app.handlers.dictionary.word_repo') as mock_word_repo:
        mock_word_repo.get_word_hebrew_by_id.return_value = "שלום"
        await confirm_delete_word(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    assert "Вы уверены" in update.callback_query.edit_message_text.call_args.args[0]
    update.callback_query.reset_mock()

    # 3. Confirm deletion
    update.callback_query.data = "dict:execute_delete:1:0"
    with patch('app.handlers.dictionary.user_dict_repo') as mock_repo:
        mock_repo.get_dictionary_page.return_value = []
        await execute_delete_word(update, context)

    mock_repo.remove_word_from_dictionary.assert_called_once_with(update.callback_query.from_user.id, 1)
    update.callback_query.edit_message_text.assert_called_once()
    assert "Ваш словарь пуст" in update.callback_query.edit_message_text.call_args.args[0]
