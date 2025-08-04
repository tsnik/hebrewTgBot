# -*- coding: utf-8 -*-

import asyncio
from typing import Tuple, Optional, Dict, Any, List
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup
from pydantic import ValidationError, TypeAdapter

from config import logger, PARSING_TIMEOUT
from dal.models import CreateCachedWord
from dal.unit_of_work import UnitOfWork
from services.parsing_strategies import (
    get_parsing_strategy,
    _get_part_of_speech_from_meta,
)
from utils import normalize_hebrew

# --- УПРАВЛЕНИЕ КОНКУРЕНТНЫМ ПАРСИНГОМ ---
PARSING_EVENTS: Dict[str, asyncio.Event] = {}
PARSING_EVENTS_LOCK = asyncio.Lock()


async def _parse_disambiguation_page(
    soup: BeautifulSoup, client: httpx.AsyncClient, base_url: str
) -> List[Dict]:
    """
    Парсит страницу неоднозначности, агрегирует результаты и добавляет логирование.
    """
    links = soup.select("div.verb-search-lemma a")
    if not links:
        logger.warning(
            '{{"event": "disambiguation_page_empty", "reason": "no_links_found"}}'
        )
        return []

    logger.info(
        f'{{"event": "disambiguation_page_found", "links_count": {len(links)}}}'
    )

    tasks = []
    for link in links:
        word_url = urljoin(base_url, link["href"])
        logger.debug(
            f'{{"event": "queueing_disambiguation_task", "url": "{word_url}"}}'
        )
        tasks.append(client.get(word_url))

    responses = await asyncio.gather(*tasks, return_exceptions=True)

    parsed_words = []
    for i, response in enumerate(responses):
        if isinstance(response, httpx.Response) and response.status_code == 200:
            word_soup = BeautifulSoup(response.text, "html.parser")
            parsed_data = _parse_single_word_page(word_soup)
            if parsed_data:
                parsed_words.append(parsed_data)
        elif isinstance(response, Exception):
            logger.error(
                f'{{"event": "disambiguation_sub_request_error", "error": "{response}"}}'
            )

    logger.info(
        f'{{"event": "disambiguation_page_parsed", "successful_parses": {len(parsed_words)}, "total_links": {len(links)}}}'
    )
    return parsed_words


def _parse_single_word_page(soup: BeautifulSoup) -> Optional[Dict]:
    """
    Определяет тип страницы, выбирает стратегию парсинга и обрабатывает результат.
    """
    logger.info('{{"event": "determine_page_type"}}')

    main_header = soup.find("h2", class_="page-header")
    if not main_header:
        logger.error(
            '{{"event": "page_type_error", "reason": "main_header_not_found"}}'
        )
        return None

    part_of_speech = _get_part_of_speech_from_meta(soup)
    # Fallback for verbs if meta tag is missing
    if not part_of_speech and (
        "спряжение" in main_header.text.lower()
        or "conjugation" in main_header.text.lower()
    ):
        part_of_speech = "verb"

    strategy = get_parsing_strategy(part_of_speech)

    if not strategy:
        logger.error(
            f'{{"event": "page_type_error", "reason": "unknown_page_type", "header": "{main_header.text.strip()}"}}'
        )
        return None

    logger.info(f'{{"event": "page_type_determined", "type": "{part_of_speech}"}}')
    parsed_data = strategy.parse(soup, main_header)

    if not parsed_data:
        logger.error(
            f'{{"event": "parsing_failed", "reason": "parser_returned_none", "page_type": "{part_of_speech}"}}'
        )
        return None

    logger.info(
        f'{{"event": "parsing_successful", "hebrew": "{parsed_data.get("hebrew", "N/A")}"}}'
    )

    return _create_word_model_from_parsed_data(parsed_data)


def _create_word_model_from_parsed_data(
    parsed_data: Dict[str, Any],
) -> Optional[CreateCachedWord]:
    """Нормализует и валидирует сырые данные парсинга, создавая модель слова."""
    try:
        hebrew = parsed_data.get("hebrew")
        if not hebrew:
            logger.error("Critical error: parsed_data is missing 'hebrew' key.")
            return None

        parsed_data["normalized_hebrew"] = normalize_hebrew(parsed_data["hebrew"])
        if parsed_data.get("conjugations"):
            for conj in parsed_data["conjugations"]:
                conj["normalized_hebrew_form"] = normalize_hebrew(conj["hebrew_form"])

        adapter = TypeAdapter(CreateCachedWord)
        validated_model = adapter.validate_python(parsed_data)
        return validated_model
    except ValidationError as e:
        logger.error(
            f"Ошибка валидации данных после парсинга для слова '{parsed_data.get('hebrew')}': {e}"
        )
        return None


async def fetch_and_cache_word_data(search_word: str) -> Tuple[str, List[Dict]]:
    """
    Асинхронная функция-диспетчер парсинга. Нормализует, ищет, парсит и сохраняет данные.
    """
    normalized_search_word = normalize_hebrew(search_word)
    parsed_data_list = None

    logger.info(
        f'{{"event": "fetch_start", "search_word": "{search_word}", "normalized": "{normalized_search_word}"}}'
    )

    async with PARSING_EVENTS_LOCK:
        if normalized_search_word not in PARSING_EVENTS:
            PARSING_EVENTS[normalized_search_word] = asyncio.Event()
            is_owner = True
        else:
            is_owner = False
        event = PARSING_EVENTS[normalized_search_word]

    if not is_owner:
        logger.info(
            f'{{"event": "awaiting_another_task", "search_word": "{search_word}"}}'
        )
        try:
            await asyncio.wait_for(event.wait(), timeout=PARSING_TIMEOUT)
            logger.info(
                f'{{"event": "await_finished", "search_word": "{search_word}"}}'
            )
            with UnitOfWork() as uow:
                results = uow.words.find_words_by_normalized_form(
                    normalized_search_word
                )
            if len(results) > 0:
                logger.info(
                    f'{{"event": "found_in_cache_after_await", "status": "ok", "results_count": {len(results)}}}'
                )
                return "ok", results
            logger.warning(
                '{{"event": "not_found_in_cache_after_await", "status": "not_found"}}'
            )
            return "not_found", None
        except asyncio.TimeoutError:
            logger.error(
                f'{{"event": "await_timeout", "status": "error", "search_word": "{search_word}"}}'
            )
            return "error", None

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 ..."}, follow_redirects=True
        ) as client:
            search_url_ru = f"https://www.pealim.com/ru/search/?q={quote(search_word)}"
            logger.debug(f'{{"event": "http_request", "url": "{search_url_ru}"}}')
            try:
                response = await client.get(search_url_ru, timeout=10)
                response.raise_for_status()

                if "/dict/" not in str(response.url):
                    search_soup = BeautifulSoup(response.text, "html.parser")
                    parsed_data_list = await _parse_disambiguation_page(
                        search_soup, client, str(response.url)
                    )
                else:  # Если сразу попали на страницу слова
                    word_soup = BeautifulSoup(response.text, "html.parser")
                    single_word = _parse_single_word_page(word_soup)
                    parsed_data_list = [single_word] if single_word else []

                if not parsed_data_list:
                    logger.warning(
                        f'{{"event": "parsing_failed", "status": "not_found", "search_word": "{search_word}"}}'
                    )
                    return "not_found", None

                logger.info(
                    f'{{"event": "parsing_success", "results_count": {len(parsed_data_list)}}}'
                )

            except httpx.RequestError as e:
                logger.error(
                    f'{{"event": "network_error", "status": "error", "error_message": "{e}"}}',
                    exc_info=True,
                )
                return "error", None

        word_ids = []

        with UnitOfWork() as uow:
            for word_data in parsed_data_list:
                # Проверка на дубликаты перед созданием
                existing_words = uow.words.find_words_by_normalized_form(
                    word_data.normalized_hebrew
                )
                is_duplicate = any(
                    w.hebrew == word_data.hebrew
                    and w.part_of_speech == word_data.part_of_speech
                    for w in existing_words
                )

                if not is_duplicate:
                    word_id = uow.words.create_cached_word(word_data)
                    word_ids.append(word_id)
                    logger.debug(
                        f'{{"event": "word_cached_to_db", "word_id": {word_id}, "hebrew": "{word_data.hebrew}"}}'
                    )
                else:
                    # Если слово уже есть, находим его ID для возврата
                    existing_word = next(
                        (w for w in existing_words if w.hebrew == word_data.hebrew),
                        None,
                    )
                    if existing_word:
                        word_id = existing_word.word_id
                        word_ids.append(word_id)

        final_words_data = []
        with UnitOfWork() as uow:
            for word_id in word_ids:
                result = uow.words.get_word_by_id(word_id)
                if result:
                    final_words_data.append(result)

        logger.info(
            f'{{"event": "fetch_success", "status": "ok", "final_count": {len(final_words_data)}}}'
        )
        return "ok", final_words_data

    except Exception as e:
        logger.error(
            f'{{"event": "critical_error", "status": "error", "error_message": "{e}"}}',
            exc_info=True,
        )
        return "error", None
    finally:
        async with PARSING_EVENTS_LOCK:
            if normalized_search_word in PARSING_EVENTS:
                PARSING_EVENTS[normalized_search_word].set()
                del PARSING_EVENTS[normalized_search_word]
                logger.debug(
                    f'{{"event": "parsing_event_cleared", "search_word": "{search_word}"}}'
                )
