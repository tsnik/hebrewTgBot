import pytest
import httpx
import respx
from bs4 import BeautifulSoup
from unittest.mock import MagicMock, AsyncMock

from services.parser import fetch_and_cache_word_data
from dal.unit_of_work import UnitOfWork


@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_word_data_direct_hit(monkeypatch):
    search_word = "לִכְתּוֹב"
    dict_url = "https://www.pealim.com/ru/dict/1/"
    mock_url = f"https://www.pealim.com/ru/search/?q={search_word}"

    # Mock the redirect
    respx.get(mock_url).mock(return_value=httpx.Response(302, headers={'location': dict_url}))
    respx.get(dict_url).mock(return_value=httpx.Response(200, text=verb_html_fixture()))

    mock_uow = MagicMock()
    mock_word = MagicMock()
    mock_word.model_dump.return_value = {'hebrew': search_word}

    # First call to find_word_by_normalized_form returns None, second call returns the mock_word
    mock_uow.__enter__().words.find_word_by_normalized_form.side_effect = [None, None, mock_word]

    monkeypatch.setattr("services.parser.UnitOfWork", lambda: mock_uow)

    status, data = await fetch_and_cache_word_data(search_word)

    assert status == "ok"
    assert data is not None
    assert data['hebrew'] == search_word
    mock_uow.__enter__().words.create_cached_word.assert_called_once()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_word_data_search_hit(monkeypatch):
    search_word = "כותב"
    final_word = "לִכְתּוֹב"
    search_url = f"https://www.pealim.com/ru/search/?q={search_word}"
    dict_url = "https://www.pealim.com/ru/dict/1/"

    search_html = f"<html><body><div class='results-by-verb'><a href='{dict_url}'></a></div></body></html>"

    respx.get(search_url).mock(return_value=httpx.Response(200, text=search_html))
    respx.get(dict_url).mock(return_value=httpx.Response(200, text=verb_html_fixture()))

    mock_uow = MagicMock()
    mock_word = MagicMock()
    mock_word.model_dump.return_value = {'hebrew': final_word}

    # First call to find_word_by_normalized_form returns None, second call returns the mock_word
    mock_uow.__enter__().words.find_word_by_normalized_form.side_effect = [None, None, mock_word]

    monkeypatch.setattr("services.parser.UnitOfWork", lambda: mock_uow)

    status, data = await fetch_and_cache_word_data(search_word)

    assert status == "ok"
    assert data is not None
    assert data['hebrew'] == final_word
    mock_uow.__enter__().words.create_cached_word.assert_called_once()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_word_data_not_found(monkeypatch):
    search_word = "איןמילהכזה"
    mock_url = f"https://www.pealim.com/ru/search/?q={search_word}"
    respx.get(mock_url).mock(return_value=httpx.Response(200, text="<html><body></body></html>"))

    mock_uow = MagicMock()
    monkeypatch.setattr("app.services.parser.UnitOfWork", lambda: mock_uow)

    status, data = await fetch_and_cache_word_data(search_word)

    assert status == "not_found"
    assert data is None
    mock_uow.words.create_cached_word.assert_not_called()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_word_data_network_error(monkeypatch):
    search_word = "מילה"
    mock_url = f"https://www.pealim.com/ru/search/?q={search_word}"
    respx.get(mock_url).mock(side_effect=httpx.RequestError("mock error"))

    mock_uow = MagicMock()
    monkeypatch.setattr("app.services.parser.UnitOfWork", lambda: mock_uow)

    status, data = await fetch_and_cache_word_data(search_word)

    assert status == "error"
    assert data is None
    mock_uow.__enter__().words.create_cached_word.assert_not_called()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_word_data_invalid_page(monkeypatch):
    search_word = "מילה"
    mock_url = f"https://www.pealim.com/ru/search/?q={search_word}"
    respx.get(mock_url).mock(return_value=httpx.Response(200, text="<html><body><h2 class='page-header'>Invalid</h2></body></html>"))

    mock_uow = MagicMock()
    monkeypatch.setattr("app.services.parser.UnitOfWork", lambda: mock_uow)

    status, data = await fetch_and_cache_word_data(search_word)

    assert status == "not_found"
    assert data is None
    mock_uow.__enter__().words.create_cached_word.assert_not_called()


def verb_html_fixture():
    return """
    <html>
        <head><title>Test Verb</title></head>
        <body>
            <h2 class="page-header">спряжение глагола</h2>
            <div>
                <div id="INF-L">
                    <span class="menukad">לִכְתּוֹב</span>
                    <div class="transcription">likhtov</div>
                </div>
                <div class="lead">to write</div>
                <p><b>биньян:</b> פעל</p>
                <p><b>корень:</b> <span class="menukad">כ-ת-ב</span></p>
                <div id="AP-M-S">
                    <span class="menukad">כּוֹתֵב</span>
                    <div class="transcription">kotev</div>
                </div>
            </div>
        </body>
    </html>
    """

@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_word_data_already_in_cache(monkeypatch):
    search_word = "לִכְתּוֹב"
    mock_url = f"https://www.pealim.com/ru/search/?q={search_word}"
    respx.get(mock_url).mock(return_value=httpx.Response(200, text=""))

    mock_uow = MagicMock()
    mock_word = MagicMock()
    mock_word.model_dump.return_value = {'hebrew': search_word}
    mock_uow.__enter__().words.find_word_by_normalized_form.return_value = mock_word
    monkeypatch.setattr("services.parser.UnitOfWork", lambda: mock_uow)

    status, data = await fetch_and_cache_word_data(search_word)

    assert status == "ok"
    assert data['hebrew'] == search_word
    mock_uow.__enter__().words.create_cached_word.assert_not_called()


import asyncio

@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_word_data_concurrent_parsing(monkeypatch):
    search_word = "לִכְתּוֹב"

    mock_uow = MagicMock()
    mock_word = MagicMock()
    mock_word.model_dump.return_value = {'hebrew': search_word}

    # Simulate that the word is not in the cache initially, but is found after the wait
    mock_uow.__enter__().words.find_word_by_normalized_form.side_effect = [None, mock_word]
    monkeypatch.setattr("services.parser.UnitOfWork", lambda: mock_uow)

    async def mock_wait():
        return

    monkeypatch.setattr("asyncio.Event.wait", mock_wait)

    # By not mocking the request, we ensure that the function will wait for the event
    status, data = await fetch_and_cache_word_data(search_word)

    assert status == "ok"
    assert data['hebrew'] == search_word


@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_word_data_timeout(monkeypatch):
    search_word = "לִכְתּוֹב"

    mock_uow = MagicMock()
    mock_uow.__enter__().words.find_word_by_normalized_form.return_value = None
    monkeypatch.setattr("services.parser.UnitOfWork", lambda: mock_uow)

    async def mock_wait():
        raise asyncio.TimeoutError

    monkeypatch.setattr("asyncio.Event.wait", mock_wait)

    # By not mocking the request, we ensure that the function will wait for the event
    status, data = await fetch_and_cache_word_data(search_word)

    assert status == "error"
    assert data is None
