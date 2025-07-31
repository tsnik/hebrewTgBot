import pytest
import httpx
import respx
from unittest.mock import MagicMock
import asyncio

from services.parser import fetch_and_cache_word_data, PARSING_EVENTS
from utils import normalize_hebrew
from dal.models import (
    CachedWord,
    CreateVerb,
    PartOfSpeech,
    CreateTranslation,
    CreateVerbConjugation,
    Binyan,
    Translation,
    Tense,
    Person,
)
from datetime import datetime


@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_new_word_successfully(monkeypatch):
    """
    Тест: успешное получение, парсинг (замоканный) и кэширование нового слова.
    Фокус: проверка, что `create_cached_word` вызывается с правильными данными.
    """
    search_word = "כותב"
    final_hebrew_word = "לִכְתּוֹב"
    search_url = f"https://www.pealim.com/ru/search/?q={search_word}"
    dict_url = "https://www.pealim.com/ru/dict/1-lichtov/"
    word_html = "<html><body>Some content</body></html>"

    # Мокируем HTTP-ответы
    respx.get(search_url).mock(
        return_value=httpx.Response(302, headers={"location": dict_url})
    )
    respx.get(dict_url).mock(return_value=httpx.Response(200, text=word_html))

    conjugations = [
        CreateVerbConjugation(
            tense=Tense.PRESENT,
            person=Person.MS,
            hebrew_form="כּוֹתֵב",
            normalized_hebrew_form="כותב",
            transcription="kotev",
        )
    ]

    # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Мокируем результат парсинга ---
    mock_parsed_object = CreateVerb(
        hebrew=final_hebrew_word,
        normalized_hebrew=normalize_hebrew(final_hebrew_word),
        transcription="likhtov",
        part_of_speech=PartOfSpeech.VERB,
        binyan=Binyan.PAAL,
        root="כ-ת-ב",
        translations=[CreateTranslation(translation_text="to write", is_primary=True)],
        conjugations=conjugations,
    )
    monkeypatch.setattr(
        "services.parser._parse_single_word_page",
        MagicMock(return_value=mock_parsed_object),
    )

    # Настраиваем мок UnitOfWork
    mock_uow = MagicMock()
    mock_uow.__enter__().words.find_words_by_normalized_form.return_value = []
    mock_uow.__enter__().words.create_cached_word.return_value = 10

    # Создаем ПОЛНОСТЬЮ ВАЛИДНЫЙ объект CachedWord для возврата из get_word_by_id
    final_word_from_db = CachedWord(
        word_id=10,
        fetched_at=datetime.now(),
        hebrew=mock_parsed_object.hebrew,
        normalized_hebrew=mock_parsed_object.normalized_hebrew,
        transcription=mock_parsed_object.transcription,
        part_of_speech=mock_parsed_object.part_of_speech,
        binyan=mock_parsed_object.binyan,
        root=mock_parsed_object.root,
        translations=[
            Translation(
                translation_id=1,
                word_id=10,
                translation_text="to write",
                is_primary=True,
            )
        ],
    )
    mock_uow.__enter__().words.get_word_by_id.return_value = final_word_from_db
    monkeypatch.setattr("services.parser.UnitOfWork", lambda: mock_uow)

    # --- Выполнение ---
    status, data = await fetch_and_cache_word_data(search_word)

    # --- Проверки ---
    assert status == "ok"
    assert len(data) == 1
    assert data[0].word_id == 10
    assert data[0].hebrew == final_hebrew_word
    mock_uow.__enter__().words.create_cached_word.assert_called_once_with(
        mock_parsed_object
    )


@pytest.mark.asyncio
@respx.mock
async def test_fetch_and_cache_word_already_in_cache(monkeypatch):
    """
    Тест: слово найдено в кэше после парсинга, `create_cached_word` НЕ вызывается.
    """
    search_word = "כותב"
    final_hebrew_word = "לִכְתּוֹב"
    search_url = f"https://www.pealim.com/ru/search/?q={search_word}"
    dict_url = "https://www.pealim.com/ru/dict/1-lichtov/"
    word_html = "<html><body>Some content</body></html>"

    # ИСПРАВЛЕНИЕ: Добавляем мок для второго запроса, который возникает после редиректа.
    respx.get(search_url).mock(
        return_value=httpx.Response(302, headers={"location": dict_url})
    )
    respx.get(dict_url).mock(return_value=httpx.Response(200, text=word_html))

    # Мокируем результат парсинга
    conjugations = [
        CreateVerbConjugation(
            tense=Tense.PRESENT,
            person=Person.MS,
            hebrew_form="כּוֹתֵב",
            normalized_hebrew_form="כותב",
            transcription="kotev",
        )
    ]

    mock_parsed_object = CreateVerb(
        hebrew=final_hebrew_word,
        normalized_hebrew=normalize_hebrew(final_hebrew_word),
        transcription="likhtov",
        part_of_speech=PartOfSpeech.VERB,
        translations=[CreateTranslation(translation_text="to write", is_primary=True)],
        conjugations=conjugations,
    )
    monkeypatch.setattr(
        "services.parser._parse_single_word_page",
        MagicMock(return_value=mock_parsed_object),
    )

    # Настраиваем мок UnitOfWork
    mock_uow = MagicMock()

    existing_word_in_db = CachedWord(
        word_id=10,
        fetched_at=datetime.now(),
        hebrew=mock_parsed_object.hebrew,
        normalized_hebrew=mock_parsed_object.normalized_hebrew,
        transcription=mock_parsed_object.transcription,
        part_of_speech=mock_parsed_object.part_of_speech,
        translations=[
            Translation(
                translation_id=1,
                word_id=10,
                translation_text="to write",
                is_primary=True,
            )
        ],
    )
    mock_uow.__enter__().words.find_words_by_normalized_form.return_value = [
        existing_word_in_db
    ]
    mock_uow.__enter__().words.get_word_by_id.return_value = existing_word_in_db
    monkeypatch.setattr("services.parser.UnitOfWork", lambda: mock_uow)

    # Выполнение
    status, data = await fetch_and_cache_word_data(search_word)

    # Проверки
    assert status == "ok"
    assert len(data) == 1
    assert data[0].word_id == 10
    mock_uow.__enter__().words.get_word_by_id.assert_called_once_with(
        existing_word_in_db.word_id
    )
    mock_uow.__enter__().words.create_cached_word.assert_not_called()


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
    mock_word_obj = CachedWord(
        word_id=1,
        hebrew=search_word,
        normalized_hebrew=normalized_word,
        part_of_speech=PartOfSpeech.VERB,
        fetched_at=datetime.now(),
        translations=[
            Translation(
                translation_id=1,
                word_id=1,
                translation_text="to write",
                is_primary=True,
            )
        ],
    )

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
    assert data[0].hebrew == search_word

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
