# tests/integration/test_search_and_add.py
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, PropertyMock
import unicodedata
import httpx

from handlers.search import handle_text_message, add_word_to_dictionary
from config import CB_ADD
from dal.unit_of_work import UnitOfWork

TEST_USER_ID = 123456789
TEST_CHAT_ID = 987654321


@pytest.fixture(scope="module")
def fixtures_path() -> Path:
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def MOCK_PEALIM_WORD_HTML(fixtures_path: Path) -> str:
    with open(fixtures_path / "2811-bdika.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def MOCK_PEALIM_SEARCH_HTML(fixtures_path: Path) -> str:
    with open(fixtures_path / "search-bdika.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def MOCK_VERB_WORD_HTML(fixtures_path: Path) -> str:
    with open(fixtures_path / "1-lichtov.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def MOCK_VERB_SEARCH_HTML(fixtures_path: Path) -> str:
    with open(fixtures_path / "search-lichtov.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def mock_search_html(request):
    return request.getfixturevalue(request.param)


@pytest.fixture
def mock_word_html(request):
    return request.getfixturevalue(request.param)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mock_search_html, mock_word_html, search_word, word_hebrew, word_hebrew_normalized",
    [
        ("MOCK_PEALIM_SEARCH_HTML", "MOCK_PEALIM_WORD_HTML", "בדיקה", "בְּדִיקָה", "בדיקה"),
        ("MOCK_VERB_SEARCH_HTML", "MOCK_VERB_WORD_HTML", "כותב", "לִכְתֹּב", "לכתב"),
    ],
    indirect=["mock_search_html", "mock_word_html"],
)
@patch("services.parser.httpx.AsyncClient")
async def test_full_search_and_add_scenario(
    mock_async_client,
    mock_context,
    mock_search_html,
    mock_word_html,
    search_word,
    word_hebrew,
    word_hebrew_normalized,
):
    async def side_effect_get(url, **kwargs):
        request = httpx.Request("GET", url)
        if "/search/" in str(url):
            response = httpx.Response(200, text=mock_search_html, request=request)
        else:
            response = httpx.Response(200, text=mock_word_html, request=request)
        return response

    mock_async_client.return_value.__aenter__.return_value.get.side_effect = (
        side_effect_get
    )

    # --- Часть 1: Поиск нового слова ---
    search_update = Mock()
    search_update.message = AsyncMock()
    search_update.message.text = search_word
    search_update.message.reply_text.return_value = AsyncMock(message_id=111)
    type(search_update).effective_user = PropertyMock(
        return_value=Mock(id=TEST_USER_ID)
    )
    type(search_update).effective_chat = PropertyMock(
        return_value=Mock(id=TEST_CHAT_ID)
    )

    with patch(
        "handlers.search.display_word_card", new_callable=AsyncMock
    ) as mock_display_word_card:
        await handle_text_message(search_update, mock_context)

        mock_display_word_card.assert_called_once()

        # --- КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ ---
        # Извлекаем данные из позиционных аргументов (args), а не именованных (kwargs).
        # `word_data` - это 4-й по счету аргумент (индекс 3).
        call_args = mock_display_word_card.call_args.args
        word_data = call_args[3]

        assert word_data.hebrew == unicodedata.normalize("NFD", word_hebrew)

    # --- Часть 2: Добавление слова в личный словарь ---
    with UnitOfWork() as uow:
        found_words = uow.words.find_words_by_normalized_form(word_hebrew_normalized)
        assert len(found_words) == 1
        word_id = found_words[0].word_id

    add_update = Mock()
    mock_query = AsyncMock()
    mock_query.message = AsyncMock(chat_id=TEST_CHAT_ID, message_id=111)
    type(add_update).callback_query = mock_query
    callback_prefix = ":".join(CB_ADD.split(":")[:2])
    type(mock_query).data = PropertyMock(return_value=f"{callback_prefix}:{word_id}")
    type(mock_query).from_user = PropertyMock(return_value=Mock(id=TEST_USER_ID))

    with patch(
        "handlers.search.display_word_card", new_callable=AsyncMock
    ) as mock_display_after_add:
        await add_word_to_dictionary(add_update, mock_context)

        # Здесь мы можем проверить kwargs, так как `in_dictionary` передается как именованный аргумент
        assert mock_display_after_add.call_args.kwargs["in_dictionary"] is True

    with UnitOfWork() as uow:
        assert uow.user_dictionary.is_word_in_dictionary(TEST_USER_ID, word_id)
