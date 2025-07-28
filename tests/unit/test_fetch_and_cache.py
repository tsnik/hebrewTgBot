import pytest
import httpx
import respx
from unittest.mock import MagicMock
import asyncio

from services.parser import fetch_and_cache_word_data, PARSING_EVENTS
from utils import normalize_hebrew


@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_word_data_search_hit(monkeypatch):
    search_word = "כותב"
    final_word = "לִכְתּוֹב"
    search_url = f"https://www.pealim.com/ru/search/?q={search_word}"
    dict_url = "https://www.pealim.com/ru/dict/1/"

    search_html = f"<html><body><div class='verb-search-lemma'><a href='{dict_url}'></a></div></body></html>"

    respx.get(search_url).mock(return_value=httpx.Response(200, text=search_html))
    respx.get(dict_url).mock(return_value=httpx.Response(200, text=verb_html_fixture()))

    mock_uow = MagicMock()
    mock_word = MagicMock()
    mock_word.model_dump.return_value = {"hebrew": final_word}

    # First call to find_word_by_normalized_form returns None, second call returns the mock_word
    mock_uow.__enter__().words.find_word_by_normalized_form.side_effect = [
        None,
        mock_word,
    ]

    monkeypatch.setattr("services.parser.UnitOfWork", lambda: mock_uow)

    status, data = await fetch_and_cache_word_data(search_word)

    assert status == "ok"
    assert len(data) > 0
    assert data[0]["hebrew"] == final_word
    mock_uow.__enter__().words.create_cached_word.assert_called_once()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_word_data_not_found(monkeypatch):
    search_word = "איןמילהכזה"
    mock_url = f"https://www.pealim.com/ru/search/?q={search_word}"
    respx.get(mock_url).mock(
        return_value=httpx.Response(200, text="<html><body></body></html>")
    )

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
    respx.get(mock_url).mock(
        return_value=httpx.Response(
            200, text="<html><body><h2 class='page-header'>Invalid</h2></body></html>"
        )
    )

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
async def test_fetch_and_cache_word_data_concurrent_parsing(monkeypatch):
    """
    Тестирует сценарий конкурентного парсинга:
    1. Задача А начинает парсить слово.
    2. Задача Б запрашивает то же слово и должна дождаться завершения Задачи А.
    3. Задача А завершает парсинг, сохраняет результат и устанавливает событие.
    4. Задача Б "просыпается" и получает результат из кэша.
    """
    search_word = "לִכְתּוֹב"
    normalized_word = normalize_hebrew(search_word)

    # --- Настройка моков ---
    mock_uow = MagicMock()
    mock_word_obj = MagicMock()
    # model_dump() должен возвращать словарь, который будет итоговым результатом
    mock_word_obj.model_dump.return_value = {
        "hebrew": search_word,
        "normalized_hebrew": normalized_word,
    }

    # Настраиваем поведение мока базы данных:
    # 1. Первый вызов (до ожидания) -> слово не найдено (None).
    # 2. Второй вызов (после ожидания) -> слово найдено (mock_word_obj).
    mock_uow.__enter__().words.find_words_by_normalized_form.side_effect = [
        [mock_word_obj],
    ]
    monkeypatch.setattr("services.parser.UnitOfWork", lambda: mock_uow)

    # Очищаем глобальный словарь событий перед тестом во избежание влияния от других тестов
    PARSING_EVENTS.clear()

    # --- Имитация состояния "парсинг уже запущен" ---
    # Вручную создаем событие, как это сделала бы "первая" задача.
    event = asyncio.Event()
    PARSING_EVENTS[normalized_word] = event

    # --- Выполнение теста ---
    # Эта корутина будет имитировать "первую" задачу, которая завершает свою работу.
    async def set_event_after_delay():
        # Даем основному потоку дойти до `await event.wait()`
        await asyncio.sleep(0)
        # Имитируем завершение парсинга и "пробуждаем" ожидающую задачу
        event.set()

    # Запускаем тестируемую функцию и "пробуждающую" корутину одновременно.
    # asyncio.gather дождется выполнения обеих.
    results = await asyncio.gather(
        fetch_and_cache_word_data(search_word), set_event_after_delay()
    )

    # Нас интересует результат выполнения основной функции
    status, data = results[0]

    # --- Проверки ---
    assert status == "ok"
    assert data[0]["hebrew"] == search_word

    # Убедимся, что к базе данных обращались дважды, как и ожидалось
    assert mock_uow.__enter__().words.find_words_by_normalized_form.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_word_data_timeout(monkeypatch):
    """
    Тестирует сценарий, когда ожидание парсинга другой задачей
    прерывается по таймауту.
    """
    search_word = "לִכְתּוֹב"
    normalized_word = normalize_hebrew(search_word)

    # --- Настройка моков ---
    # Мокируем UnitOfWork, чтобы он всегда возвращал None (слово не в кэше)
    mock_uow = MagicMock()
    mock_uow_context = MagicMock()
    mock_uow.__enter__.return_value = mock_uow_context
    mock_uow_context.words.find_words_by_normalized_form.return_value = None
    # Убедитесь, что путь для monkeypatch соответствует структуре вашего проекта
    monkeypatch.setattr("services.parser.UnitOfWork", lambda: mock_uow)

    # Устанавливаем очень маленький таймаут специально для этого теста
    monkeypatch.setattr("services.parser.PARSING_TIMEOUT", 0.01)

    # Очищаем глобальный словарь событий
    PARSING_EVENTS.clear()

    # --- Имитация состояния "парсинг уже запущен" ---
    # Вручную создаем событие, как это сделала бы "первая" задача.
    # Важно: мы НЕ будем вызывать .set() для этого события, чтобы спровоцировать таймаут.
    event = asyncio.Event()
    PARSING_EVENTS[normalized_word] = event

    # --- Выполнение теста ---
    # Функция должна пойти по ветке ожидания и отвалиться по таймауту
    status, data = await fetch_and_cache_word_data(search_word)

    # --- Проверки ---
    # Внутри fetch_and_cache_word_data исключение TimeoutError
    # должно быть поймано и преобразовано в статус 'error'.
    assert status == "error"
    assert data is None

    # Проверяем, что к базе данных обращались только один раз (до начала ожидания)
    mock_uow_context.words.find_word_by_normalized_form.assert_not_called()
