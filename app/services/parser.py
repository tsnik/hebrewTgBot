# -*- coding: utf-8 -*-

import re
import asyncio
import unicodedata
from typing import Tuple, Optional, Dict, Any, List
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from config import logger, PARSING_TIMEOUT
from dal.unit_of_work import UnitOfWork
from utils import normalize_hebrew, parse_translations

# --- УПРАВЛЕНИЕ КОНКУРЕНТНЫМ ПАРСИНГОМ ---
PARSING_EVENTS: Dict[str, asyncio.Event] = {}
PARSING_EVENTS_LOCK = asyncio.Lock()


BINYAN_HTML_MAP = {
    "пааль": "paal",
    "пиэль": "piel",
    "hифъиль": "hifil",
    "нифъаль": "nifal",
    "hитпаэль": "hitpael",
    "hифъаль": "hufal",
    "пуаль": "pual",
}


def _extract_form_value(cell: Tag) -> str:
    """Извлекает иврит и транскрипцию из ячейки таблицы."""
    menukad = cell.find(class_="menukad")
    transcription = cell.find(class_="transcription")

    hebrew_part = menukad.text.strip() if menukad else ""
    trans_part = transcription.text.strip() if transcription else ""

    if hebrew_part and trans_part:
        return f"{hebrew_part} ({trans_part})"
    return hebrew_part or trans_part


def _extract_hebrew_from_cell(cell: Tag) -> Optional[str]:
    """Извлекает только ивритскую форму из ячейки таблицы, без транскрипции."""
    if not cell:
        return None
    menukad = cell.find(class_="menukad")
    if not menukad:
        return None
    # Убираем альтернативные написания типа "~ ..."
    hebrew_text = menukad.text.split("~")[0].strip()
    # Нормализуем строку в NFD для консистентного сравнения
    return unicodedata.normalize("NFD", hebrew_text)


def _get_part_of_speech_from_meta(soup: BeautifulSoup) -> Optional[str]:
    """
    Извлекает часть речи из мета-тега description.
    Это наиболее надежный метод.
    """
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if not meta_tag or not meta_tag.get("content"):
        logger.warning("Мета-тег 'description' не найден или пуст.")
        return None

    content = meta_tag.get("content", "").lower()
    if content.startswith("verb"):
        return "verb"
    if content.startswith("существительное"):
        return "noun"
    if content.startswith("прилагательное"):
        return "adjective"

    logger.warning(f"Не удалось определить часть речи из мета-тега: {content[:50]}...")
    return None


def _parse_noun_forms(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Извлекает формы для существительного из таблицы.
    Сохраняет род в стандартизированном английском формате.
    """
    forms = {}
    main_header = soup.find("h2", class_="page-header")
    if main_header:
        p_tag = main_header.find_next_sibling("p")
        if p_tag:
            text = p_tag.text.lower()
            if "мужской род" in text or "masculine" in text:
                forms["gender"] = "masculine"
            elif "женский род" in text or "feminine" in text:
                forms["gender"] = "feminine"

    table = soup.find("table", class_="conjugation-table")
    if not table:
        return forms

    absolute_state_header = table.find("th", string="Абсолютное состояние")
    if absolute_state_header:
        row = absolute_state_header.parent
        cells = row.find_all("td")
        if len(cells) >= 2:
            forms["singular_form"] = _extract_hebrew_from_cell(cells[0])
            forms["plural_form"] = _extract_hebrew_from_cell(cells[1])

    return forms


def _parse_adjective_forms(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Извлекает формы для прилагательного из таблицы.
    Теперь использует _extract_hebrew_from_cell для чистоты данных.
    """
    forms = {}
    table = soup.find("table", class_="conjugation-table")
    if not table:
        return forms

    data_row = table.find("tbody").find("tr")
    if not data_row:
        return forms

    cells = data_row.find_all("td")
    if len(cells) == 4:
        forms["masculine_singular"] = _extract_hebrew_from_cell(cells[0])
        forms["feminine_singular"] = _extract_hebrew_from_cell(cells[1])
        forms["masculine_plural"] = _extract_hebrew_from_cell(cells[2])
        forms["feminine_plural"] = _extract_hebrew_from_cell(cells[3])
    return forms


def parse_verb_page(soup: BeautifulSoup, main_header: Tag) -> Optional[Dict[str, Any]]:
    """Парсер для страниц глаголов."""
    logger.info("-> Запущен parse_verb_page.")
    try:
        data = {"part_of_speech": "verb", "is_verb": True}

        logger.info("--> parse_verb_page: Поиск инфинитива...")
        infinitive_div = soup.find("div", id="INF-L")

        if not infinitive_div:
            logger.error("--> parse_verb_page: Не найден блок инфинитива.")
            return None

        menukad_tag = infinitive_div.find("span", class_="menukad")
        if not menukad_tag:
            logger.error(
                "--> parse_verb_page: Не найден тег menukad внутри блока инфинитива."
            )
            return None

        hebrew_text = menukad_tag.text.split("~")[0].strip()
        data["hebrew"] = unicodedata.normalize("NFD", hebrew_text)
        logger.info(f"--> parse_verb_page: Инфинитив найден: {data['hebrew']}")

        logger.info("--> parse_verb_page: Поиск перевода...")
        lead_div = soup.find("div", class_="lead")
        if not lead_div:
            logger.error(
                f"--> parse_verb_page для '{data['hebrew']}': не найден 'div' с классом 'lead' (перевод)."
            )
            return None
        data["translations"] = parse_translations(lead_div.text.strip())
        if not data["translations"]:
            logger.warning(
                f"--> parse_verb_page для '{data['hebrew']}': функция parse_translations вернула пустой список."
            )
            return None
        logger.info("--> parse_verb_page: Переводы найдены.")

        logger.info("--> parse_verb_page: Поиск транскрипции...")
        transcription_div = infinitive_div.find("div", class_="transcription")
        data["transcription"] = (
            transcription_div.text.strip() if transcription_div else ""
        )

        logger.info("--> parse_verb_page: Поиск корня и биньяна...")
        data["root"], data["binyan"] = None, None
        for p in main_header.parent.find_all("p"):
            text_lower = p.text.lower()
            if "глагол" in text_lower:
                binyan_text = (
                    p.text.replace("Verb –", "").replace("Глагол –", "").strip()
                )
                data["binyan"] = binyan_text.split()[0] if binyan_text else None
                data["binyan"] = BINYAN_HTML_MAP.get(
                    data["binyan"].lower(), data["binyan"]
                )

            if "root" in text_lower or "корень" in text_lower:
                root_tag = p.find("span", class_="menukad")
                if root_tag:
                    data["root"] = root_tag.text.strip()

        logger.info("--> parse_verb_page: Поиск спряжений...")
        conjugations = []
        verb_forms = soup.find_all("div", id=re.compile(r"^(AP|PERF|IMPF|IMP|INF)-"))
        for form in verb_forms:
            form_id, menukad_tag, trans_tag = (
                form.get("id"),
                form.find("span", class_="menukad"),
                form.find("div", class_="transcription"),
            )
            if all([form_id, menukad_tag, trans_tag]):
                tense_prefix = form_id.split("-")[0].lower()
                person = (
                    form_id.split("-")[1] if len(form_id.split("-")) > 1 else "форма"
                )
                conjugations.append(
                    {
                        "tense": tense_prefix,
                        "person": person,
                        "hebrew_form": menukad_tag.text.strip(),
                        "transcription": trans_tag.text.strip(),
                    }
                )
        data["conjugations"] = conjugations
        logger.info(f"--> parse_verb_page: Найдено {len(conjugations)} форм спряжений.")

        logger.info("-> parse_verb_page завершен успешно.")
        return data
    except Exception as e:
        logger.error(f"Ошибка в parse_verb_page: {e}", exc_info=True)
        return None


def parse_noun_or_adjective_page(
    soup: BeautifulSoup, main_header: Tag
) -> Optional[Dict[str, Any]]:
    """
    Парсер для страниц существительных и прилагательных.
    Ищет каноническую форму непосредственно в таблице склонения.
    """
    part_of_speech = _get_part_of_speech_from_meta(soup)
    if not part_of_speech or part_of_speech == "verb":
        logger.error(f"Неверный тип страницы для этого парсера: {part_of_speech}")
        return None

    logger.info(f"-> Запущен parse_noun_or_adjective_page для '{part_of_speech}'.")
    try:
        data = {
            "root": None,
            "binyan": None,
            "conjugations": [],
            "part_of_speech": part_of_speech,
            "is_verb": False,
        }

        logger.info(f"--> Часть речи установлена как {data['part_of_speech']}.")

        logger.info("--> Поиск канонической формы из таблицы...")
        canonical_hebrew = None
        table = soup.find("table", class_="conjugation-table")

        if table:
            if part_of_speech == "noun":
                # Ищем "Абсолютное состояние", затем первую ячейку данных (ед.ч.)
                header_cell = table.find("th", string="Абсолютное состояние")
                if header_cell:
                    data_cell = header_cell.parent.find("td")
                    if data_cell:
                        canonical_hebrew = _extract_hebrew_from_cell(data_cell)
            elif part_of_speech == "adjective":
                # Просто берем первую ячейку данных (м.р., ед.ч.)
                data_cell = table.find("td")
                if data_cell:
                    canonical_hebrew = _extract_hebrew_from_cell(data_cell)

        if not canonical_hebrew:
            logger.error(
                "--> Не удалось найти каноническую форму в таблице. Парсинг прерван."
            )
            return None

        data["hebrew"] = canonical_hebrew
        logger.info(f"--> Каноническая форма из таблицы найдена: {data['hebrew']}")

        logger.info("--> Поиск перевода...")
        lead_div = soup.find("div", class_="lead")
        if not lead_div:
            logger.error(
                f"--> для '{data['hebrew']}': не найден 'div' с классом 'lead' (перевод)."
            )
            return None

        data["translations"] = parse_translations(lead_div.text.strip())
        if not data["translations"]:
            logger.warning(
                f"--> для '{data['hebrew']}': функция parse_translations вернула пустой список."
            )
            return None
        logger.info("--> Переводы найдены.")

        logger.info("--> Поиск транскрипции...")
        first_form = soup.find("div", class_="transcription")
        data["transcription"] = first_form.text.strip() if first_form else ""

        # Извлечение всех форм в зависимости от части речи
        if data["part_of_speech"] == "noun":
            forms = _parse_noun_forms(soup)
            data.update(forms)
        elif data["part_of_speech"] == "adjective":
            forms = _parse_adjective_forms(soup)
            data.update(forms)

        logger.info("-> parse_noun_or_adjective_page завершен успешно.")
        return data
    except Exception as e:
        logger.error(f"Ошибка в parse_noun_or_adjective_page: {e}", exc_info=True)
        return None


async def _parse_disambiguation_page(
    soup: BeautifulSoup, client: httpx.AsyncClient, base_url: str
) -> List[Dict]:
    """Парсит страницу неоднозначности и агрегирует результаты."""

    # Находим все ссылки на страницы конкретных слов
    links = soup.select("div.verb-search-lemma a")
    if not links:
        return []

    # Асинхронно запрашиваем и парсим каждую страницу
    tasks = []
    logger.info(links)
    for link in links:
        word_url = urljoin(base_url, link["href"])
        tasks.append(client.get(word_url))

    responses = await asyncio.gather(*tasks, return_exceptions=True)

    parsed_words = []
    for response in responses:
        if isinstance(response, httpx.Response) and response.status_code == 200:
            word_soup = BeautifulSoup(response.text, "html.parser")
            # Используем уже существующую логику парсинга одной страницы
            parsed_data = _parse_single_word_page(word_soup)
            if parsed_data:
                parsed_words.append(parsed_data)

    return parsed_words


def _parse_single_word_page(soup: BeautifulSoup) -> Optional[Dict]:
    logger.info("Шаг 2: Определение типа страницы...")
    main_header = soup.find("h2", class_="page-header")
    if not main_header:
        logger.error("Парсинг не удался: не найден 'h2' с классом 'page-header'.")
        return "error", None

    parsed_data = None
    # Используем мета-тег как основной источник, но оставляем проверку заголовка как запасной вариант
    part_of_speech = _get_part_of_speech_from_meta(soup)

    if (
        part_of_speech == "verb"
        or "спряжение" in main_header.text.lower()
        or "conjugation" in main_header.text.lower()
    ):
        logger.info("Шаг 2.1: Страница определена как ГЛАГОЛ.")
        parsed_data = parse_verb_page(soup, main_header)
    elif (
        part_of_speech in ["noun", "adjective"]
        or "формы слова" in main_header.text.lower()
    ):
        logger.info("Шаг 2.1: Страница определена как СУЩЕСТВИТЕЛЬНОЕ/ПРИЛАГАТЕЛЬНОЕ.")
        parsed_data = parse_noun_or_adjective_page(soup, main_header)
    else:
        logger.error(f"Не удалось определить тип страницы для: {main_header.text}")
        return None

    logger.info("Шаг 3: Обработка и НОРМАЛИЗАЦИЯ результата парсинга...")
    if not parsed_data:
        logger.error("Парсинг не удался: одна из функций парсинга вернула None.")
        return None

    logger.info(f"Шаг 3.1: Парсер успешно вернул данные для '{parsed_data['hebrew']}'.")
    parsed_data["normalized_hebrew"] = normalize_hebrew(parsed_data["hebrew"])
    if parsed_data.get("conjugations"):
        for conj in parsed_data["conjugations"]:
            conj["normalized_hebrew_form"] = normalize_hebrew(conj["hebrew_form"])

    word_to_create = {
        "hebrew": parsed_data["hebrew"],
        "normalized_hebrew": parsed_data["normalized_hebrew"],
        "transcription": parsed_data.get("transcription"),
        "is_verb": parsed_data.get("is_verb", False),
        "part_of_speech": parsed_data.get("part_of_speech"),
        "root": parsed_data.get("root"),
        "binyan": parsed_data.get("binyan"),
        "translations": parsed_data.get("translations", []),
        "conjugations": parsed_data.get("conjugations", []),
        "gender": parsed_data.get("gender"),
        "singular_form": parsed_data.get("singular_form"),
        "plural_form": parsed_data.get("plural_form"),
        "masculine_singular": parsed_data.get("masculine_singular"),
        "feminine_singular": parsed_data.get("feminine_singular"),
        "masculine_plural": parsed_data.get("masculine_plural"),
        "feminine_plural": parsed_data.get("feminine_plural"),
    }

    return word_to_create


async def fetch_and_cache_word_data(
    search_word: str,
) -> Tuple[str, List[Dict]]:
    """
    Асинхронная функция-диспетчер парсинга. Нормализует, ищет, парсит и сохраняет данные.
    """
    normalized_search_word = normalize_hebrew(search_word)
    parsed_data_list = None

    async with PARSING_EVENTS_LOCK:
        if normalized_search_word not in PARSING_EVENTS:
            PARSING_EVENTS[normalized_search_word] = asyncio.Event()
            is_owner = True
        else:
            is_owner = False
        event = PARSING_EVENTS[normalized_search_word]

    if not is_owner:
        logger.info(
            f"Парсинг для '{search_word}' уже запущен другой задачей, ожидание..."
        )
        try:
            await asyncio.wait_for(event.wait(), timeout=PARSING_TIMEOUT)
            logger.info(
                f"Ожидание для '{search_word}' завершено, повторный поиск в кэше."
            )
            with UnitOfWork() as uow:
                results = uow.words.find_words_by_normalized_form(
                    normalized_search_word
                )
            if len(results) > 0:
                return "ok", results
            return "not_found", None
        except asyncio.TimeoutError:
            logger.warning(f"Таймаут ожидания для '{search_word}'.")
            return "error", None

    try:
        logger.info(f"--- Начало парсинга для '{search_word}' ---")
        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 ..."}, follow_redirects=True
        ) as client:
            logger.info("Шаг 1: Выполнение HTTP-запроса...")
            try:
                # Сначала ищем в русской версии, если нет - в английской
                search_url_ru = (
                    f"https://www.pealim.com/ru/search/?q={quote(search_word)}"
                )
                response = await client.get(search_url_ru, timeout=10)
                response.raise_for_status()

                # Если после поиска мы не на странице словаря, ищем ссылку
                if "/dict/" not in str(response.url):
                    search_soup = BeautifulSoup(response.text, "html.parser")
                    parsed_data_list = await _parse_disambiguation_page(
                        search_soup, client, str(response.url)
                    )

                if not parsed_data_list:
                    logger.warning(
                        f"Не найдено результатов ни в русской, ни в английской версии для '{search_word}'."
                    )
                    return "not_found", None

            except httpx.RequestError as e:
                logger.error(
                    f"Сетевая ошибка при запросе к pealim.com: {e}", exc_info=True
                )
                return "error", None

        with UnitOfWork() as uow:
            for word_data in parsed_data_list:
                words = uow.words.find_words_by_normalized_form(
                    word_data["normalized_hebrew"]
                )
                word = None
                for w in words:
                    if w.hebrew == word_data["hebrew"]:
                        word = w
                        break
                if word is None:
                    word_data["word_id"] = uow.words.create_cached_word(**word_data)

        logger.info("Шаг 5: Ожидание появления слов в БД и возврат результата...")
        final_words_data = []
        with UnitOfWork() as uow:
            for word_data in parsed_data_list:
                result = uow.words.get_word_by_id(word_data["word_id"])
                if result:
                    final_words_data.append(result)
                    logger.info(
                        f"Шаг 5.x: Слово {result.normalized_hebrew} успешно найдено в БД."
                    )
        return "ok", final_words_data

    except Exception as e:
        logger.error(
            f"Критическая ошибка в fetch_and_cache_word_data: {e}", exc_info=True
        )
        return "error", None
    finally:
        logger.info(f"Шаг 6: Очистка события для '{search_word}'.")
        async with PARSING_EVENTS_LOCK:
            if normalized_search_word in PARSING_EVENTS:
                PARSING_EVENTS[normalized_search_word].set()
                del PARSING_EVENTS[normalized_search_word]
