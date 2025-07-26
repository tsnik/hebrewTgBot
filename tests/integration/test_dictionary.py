import pytest
from unittest.mock import AsyncMock, Mock, patch
from handlers.search import add_word_to_dictionary
from dal.models import CachedWord, Translation
from datetime import datetime
from dal.unit_of_work import UnitOfWork

@pytest.mark.asyncio
async def test_add_word_to_dictionary(memory_db):
    """Test adding a word to the dictionary."""
    update = Mock()
    update.callback_query = AsyncMock()
    update.callback_query.from_user.id = 123
    update.callback_query.data = "word:add:1"
    context = Mock()
    context.bot = AsyncMock()

    with UnitOfWork() as uow:
        uow.words.create_cached_word(
            hebrew='מילה',
            normalized_hebrew='מילה',
            transcription='mila',
            is_verb=False,
            root=None,
            binyan=None,
            translations=[{'translation_text': 'word', 'is_primary': True}],
            conjugations=[]
        )
        uow.commit()

    with patch('handlers.search.display_word_card'):
        await add_word_to_dictionary(update, context)

    update.callback_query.answer.assert_called_once_with("Добавлено!")
