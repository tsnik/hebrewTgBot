import pytest
from unittest.mock import AsyncMock, Mock, patch
from handlers.search import add_word_to_dictionary
from dal.models import CachedWord, Translation
from datetime import datetime
from dal.unit_of_work import UnitOfWork

@pytest.mark.asyncio
async def test_add_word_to_dictionary(memory_db_uow: UnitOfWork):
    """Test adding a word to the dictionary."""
    update = Mock()
    update.callback_query = AsyncMock()
    update.callback_query.from_user.id = 123
    update.callback_query.data = "word:add:1"
    context = Mock()
    context.bot = AsyncMock()

    word = CachedWord(word_id=1, hebrew="מילה", normalized_hebrew="מילה", transcription="mila", is_verb=False, root="", binyan="", fetched_at=datetime.now(), translations=[Translation(translation_id=1, word_id=1, translation_text="word", context_comment="", is_primary=True)])

    with patch('handlers.search.UnitOfWork') as mock_uow:
        mock_uow.return_value.__enter__.return_value.words.get_word_by_id.return_value = word
        await add_word_to_dictionary(update, context)

    update.callback_query.answer.assert_called_once_with("Добавлено!")
