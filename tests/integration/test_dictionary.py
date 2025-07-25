import pytest
from unittest.mock import AsyncMock, Mock, patch
from app.handlers.search import add_word_to_dictionary
from app.services.database import db_read_query
from app.dal.models import CachedWord, Translation
from datetime import datetime

@pytest.mark.asyncio
async def test_add_word_to_dictionary():
    """Test adding a word to the dictionary."""
    update = Mock()
    update.callback_query = AsyncMock()
    update.callback_query.from_user.id = 123
    update.callback_query.data = "add:word:1"
    context = Mock()
    context.bot = AsyncMock()

    word = CachedWord(word_id=1, hebrew="מילה", normalized_hebrew="מילה", transcription="mila", is_verb=False, root="", binyan="", fetched_at=datetime.now(), translations=[Translation(translation_id=1, word_id=1, translation_text="word", context_comment="", is_primary=True)])

    with patch('app.handlers.search.user_dict_repo.add_word_to_dictionary') as mock_add:
        with patch('app.handlers.search.word_repo.get_word_by_id', return_value=word):
            with patch('app.handlers.search.display_word_card') as mock_display:
                await add_word_to_dictionary(update, context)

    mock_add.assert_called_once_with(123, 1)
    update.callback_query.answer.assert_called_once_with("Добавлено!")
    mock_display.assert_called_once()
