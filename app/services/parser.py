# -*- coding: utf-8 -*-

import logging
import re
import sqlite3
import asyncio
import time
from datetime import datetime
from typing import Tuple, Optional, Dict, Any, List
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from config import logger, PARSING_TIMEOUT
from services.database import local_search, db_transaction, db_read_query, DB_READ_ATTEMPTS, DB_READ_DELAY
from utils import normalize_hebrew, parse_translations

# --- УПРАВЛЕНИЕ КОНКУРЕНТНЫМ ПАРСИНГОМ ---
PARSING_EVENTS: Dict[str, asyncio.Event] = {}
PARSING_EVENTS_LOCK = asyncio.Lock()


def parse_verb_page(soup: BeautifulSoup, main_header: Tag) -> Optional[Dict[str, Any]]:
    """Парсер для страниц глаголов."""
    logger.info("-> Запущен parse_verb_page.")
    try:
        data = {'is_verb': True}

        logger.info("--> parse_verb_page: Поиск инфинитива...")
        infinitive_div = soup.find('div', id='INF-L')
        if not infinitive_div:
            logger.error("--> parse_verb_page: Не найден блок инфинитива INF-L.")
            return None

        menukad_tag = infinitive_div.find('span', class_='menukad')
        if not menukad_tag:
            logger.error("--> parse_verb_page: Не найден тег menukad внутри блока инфинитива.")
            return None
        data['hebrew'] = menukad_tag.text.split('~')[0].strip()
        logger.info(f"--> parse_verb_page: Инфинитив найден: {data['hebrew']}")

        logger.info("--> parse_verb_page: Поиск перевода...")
        lead_div = soup.find('div', class_='lead')
        if not lead_div:
            logger.error(f"--> parse_verb_page для '{data['hebrew']}': не найден 'div' с классом 'lead' (перевод).")
            return None
        data['translations'] = parse_translations(lead_div.text.strip())
        if not data['translations']:
            logger.warning(f"--> parse_verb_page для '{data['hebrew']}': функция parse_translations вернула пустой список.")
            return None
        logger.info(f"--> parse_verb_page: Переводы найдены.")

        logger.info("--> parse_verb_page: Поиск транскрипции...")
        transcription_div = infinitive_div.find('div', class_='transcription')
        data['transcription'] = transcription_div.text.strip() if transcription_div else ''
        
        logger.info("--> parse_verb_page: Поиск корня и биньяна...")
        data['root'], data['binyan'] = None, None
        for p in main_header.find_next_siblings('p'):
            if 'глагол' in p.text.lower():
                binyan_tag = p.find('b')
                if binyan_tag: data['binyan'] = binyan_tag.text.strip()
            if 'корень' in p.text.lower():
                root_tag = p.find('span', class_='menukad')
                if root_tag: data['root'] = root_tag.text.strip()

        logger.info("--> parse_verb_page: Поиск спряжений...")
        conjugations = []
        verb_forms = soup.find_all('div', id=re.compile(r'^(AP|PERF|IMPF|IMP|INF)-'))
        tense_map = {'AP': 'настоящее', 'PERF': 'прошедшее', 'IMPF': 'будущее', 'IMP': 'повелительное', 'INF': 'инфинитив'}
        for form in verb_forms:
            form_id, menukad_tag, trans_tag = form.get('id'), form.find('span', class_='menukad'), form.find('div', class_='transcription')
            if all([form_id, menukad_tag, trans_tag]):
                tense_prefix = form_id.split('-')[0]
                person = form_id.split('-')[1] if len(form_id.split('-')) > 1 else "форма"
                conjugations.append({'tense': tense_map.get(tense_prefix), 'person': person, 'hebrew_form': menukad_tag.text.strip(), 'transcription': trans_tag.text.strip()})
        data['conjugations'] = conjugations
        logger.info(f"--> parse_verb_page: Найдено {len(conjugations)} форм спряжений.")

        logger.info("-> parse_verb_page завершен успешно.")
        return data
    except Exception as e:
        logger.error(f"Ошибка в parse_verb_page: {e}", exc_info=True)
        return None

def parse_noun_or_adjective_page(soup: BeautifulSoup, main_header: Tag) -> Optional[Dict[str, Any]]:
    """Парсер для страниц существительных и прилагательных."""
    logger.info("-> Запущен parse_noun_or_adjective_page.")
    try:
        data = {'is_verb': False, 'root': None, 'binyan': None, 'conjugations': []}
        
        logger.info("--> parse_noun_or_adjective_page: Поиск канонической формы...")
        canonical_hebrew = None
        canonical_tag = main_header.find('span', class_='menukad')
        if canonical_tag:
            canonical_hebrew = canonical_tag.text.strip()
        elif soup.title and '–' in soup.title.string:
            logger.info("--> parse_noun_or_adjective_page: не найден menukad, используется запасной метод (title).")
            potential_word = soup.title.string.split('–')[0].strip()
            if re.match(r'^[\u0590-\u05FF\s-]+$', potential_word):
                canonical_hebrew = potential_word

        if not canonical_hebrew:
            logger.error("--> parse_noun_or_adjective_page: Не удалось найти каноническую форму.")
            return None
        data['hebrew'] = canonical_hebrew
        logger.info(f"--> parse_noun_or_adjective_page: Каноническая форма найдена: {data['hebrew']}")
        
        logger.info("--> parse_noun_or_adjective_page: Поиск перевода...")
        lead_div = soup.find('div', class_='lead')
        if not lead_div:
            logger.error(f"--> parse_noun_or_adjective_page для '{data['hebrew']}': не найден 'div' с классом 'lead' (перевод).")
            return None
        
        data['translations'] = parse_translations(lead_div.text.strip())
        if not data['translations']:
            logger.warning(f"--> parse_noun_or_adjective_page для '{data['hebrew']}': функция parse_translations вернула пустой список.")
            return None
        logger.info(f"--> parse_noun_or_adjective_page: Переводы найдены.")

        logger.info("--> parse_noun_or_adjective_page: Поиск транскрипции...")
        transcription_div = soup.find('div', class_='transcription')
        data['transcription'] = transcription_div.text.strip() if transcription_div else ''
        
        logger.info("-> parse_noun_or_adjective_page завершен успешно.")
        return data
    except Exception as e:
        logger.error(f"Ошибка в parse_noun_or_adjective_page: {e}", exc_info=True)
        return None

async def fetch_and_cache_word_data(search_word: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Асинхронная функция-диспетчер парсинга. Нормализует, ищет, парсит и сохраняет данные.
    """
    normalized_search_word = normalize_hebrew(search_word)
    async with PARSING_EVENTS_LOCK:
        if normalized_search_word not in PARSING_EVENTS:
            PARSING_EVENTS[normalized_search_word] = asyncio.Event()
            is_owner = True
        else:
            is_owner = False
        event = PARSING_EVENTS[normalized_search_word]

    if not is_owner:
        logger.info(f"Парсинг для '{search_word}' уже запущен другой задачей, ожидание...")
        try:
            await asyncio.wait_for(event.wait(), timeout=PARSING_TIMEOUT)
            logger.info(f"Ожидание для '{search_word}' завершено, повторный поиск в кэше.")
            result = local_search(normalized_search_word)
            return ('ok', result) if result else ('not_found', None)
        except asyncio.TimeoutError:
            logger.warning(f"Таймаут ожидания для '{search_word}'.")
            return 'error', None

    try:
        logger.info(f"--- Начало парсинга для '{search_word}' ---")
        async with httpx.AsyncClient(headers={'User-Agent': 'Mozilla/5.0 ...'}, follow_redirects=True) as client:
            logger.info("Шаг 1: Выполнение HTTP-запроса...")
            try:
                search_url = f"https://www.pealim.com/ru/search/?q={quote(search_word)}"
                search_response = await client.get(search_url, timeout=10)
                search_response.raise_for_status()
                logger.info(f"Шаг 1.1: Успешно получен ответ от {search_url}")

                if "/dict/" in str(search_response.url):
                    response = search_response
                    logger.info("Шаг 1.2: Прямое перенаправление на словарную статью.")
                else:
                    logger.info("Шаг 1.2: Ответ - страница поиска, ищем нужную ссылку...")
                    search_soup = BeautifulSoup(search_response.text, 'html.parser')
                    results_container = search_soup.find('div', class_='results-by-verb') or search_soup.find('div', class_='results-by-meaning')
                    if not results_container:
                        logger.warning(f"Не найдено результатов на странице поиска для '{search_word}'.")
                        return 'not_found', None
                    result_link = results_container.find('a', href=re.compile(r'/dict/'))
                    if not result_link or not result_link.get('href'):
                        logger.warning(f"Не найдено ссылки на словарную статью для '{search_word}'.")
                        return 'not_found', None
                    final_url = urljoin(str(search_response.url), result_link['href'])
                    logger.info(f"Шаг 1.3: Найдена ссылка, переход на {final_url}")
                    response = await client.get(final_url, timeout=10)
                    response.raise_for_status()
            except httpx.RequestError as e:
                logger.error(f"Сетевая ошибка при запросе к pealim.com: {e}", exc_info=True)
                return 'error', None

        logger.info("Шаг 1.4: Финальная страница успешно загружена.")
        soup = BeautifulSoup(response.text, 'html.parser')
        
        logger.info("Шаг 2: Определение типа страницы...")
        main_header = soup.find('h2', class_='page-header')
        if not main_header:
            logger.error("Парсинг не удался: не найден 'h2' с классом 'page-header'.")
            return 'error', None

        parsed_data = None
        if "спряжение" in main_header.text.lower():
            logger.info("Шаг 2.1: Страница определена как ГЛАГОЛ.")
            parsed_data = parse_verb_page(soup, main_header)
        else:
            logger.info("Шаг 2.1: Страница определена как СУЩЕСТВИТЕЛЬНОЕ/ПРИЛАГАТЕЛЬНОЕ.")
            parsed_data = parse_noun_or_adjective_page(soup, main_header)

        if not parsed_data:
            logger.error("Парсинг не удался: одна из функций парсинга вернула None.")
            return 'error', None

        logger.info(f"Шаг 3.1: Парсер успешно вернул данные для '{parsed_data['hebrew']}'.")
        parsed_data['normalized_hebrew'] = normalize_hebrew(parsed_data['hebrew'])
        if parsed_data.get('conjugations'):
            for conj in parsed_data['conjugations']:
                conj['normalized_hebrew_form'] = normalize_hebrew(conj['hebrew_form'])
        
        if local_search(parsed_data['normalized_hebrew']):
            logger.info(f"Шаг 3.2: Нормализованная форма '{parsed_data['normalized_hebrew']}' уже есть в кэше. Сохранение не требуется.")
            return 'ok', local_search(parsed_data['normalized_hebrew'])

        logger.info(f"Шаг 4: Сохранение '{parsed_data['hebrew']}' и его форм в БД...")
        def _save_word_transaction(cursor: sqlite3.Cursor):
            cursor.execute("""
                INSERT INTO cached_words (hebrew, normalized_hebrew, transcription, is_verb, root, binyan, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                parsed_data['hebrew'], parsed_data['normalized_hebrew'], parsed_data['transcription'],
                parsed_data['is_verb'], parsed_data.get('root'), parsed_data.get('binyan'), datetime.now()
            ))
            word_id = cursor.lastrowid
            if word_id and parsed_data.get('translations'):
                translations_to_insert = [(word_id, t['translation_text'], t['context_comment'], t['is_primary']) for t in parsed_data['translations']]
                cursor.executemany("INSERT INTO translations (word_id, translation_text, context_comment, is_primary) VALUES (?, ?, ?, ?)", translations_to_insert)
            if word_id and parsed_data.get('conjugations'):
                conjugations_to_insert = [(word_id, c['tense'], c['person'], c['hebrew_form'], c['normalized_hebrew_form'], c['transcription']) for c in parsed_data['conjugations']]
                cursor.executemany("INSERT INTO verb_conjugations (word_id, tense, person, hebrew_form, normalized_hebrew_form, transcription) VALUES (?, ?, ?, ?, ?, ?)", conjugations_to_insert)
        
        db_transaction(_save_word_transaction)
        logger.info("Шаг 4.1: Транзакция на запись отправлена в очередь.")
        
        logger.info("Шаг 5: Ожидание появления слова в БД и возврат результата...")
        final_word_data = None
        for i in range(DB_READ_ATTEMPTS):
            logger.info(f"Шаг 5.{i+1}: Попытка чтения из БД...")
            final_word_data = local_search(parsed_data['normalized_hebrew'])
            if final_word_data:
                logger.info("Шаг 5.x: Слово успешно найдено в БД.")
                break
            await asyncio.sleep(DB_READ_DELAY)
        
        if final_word_data:
            logger.info(f"--- Парсинг для '{search_word}' завершен УСПЕШНО. ---")
            return 'ok', final_word_data
        else:
            logger.error(f"--- Парсинг для '{search_word}' завершен с ОШИБКОЙ БД (не удалось прочитать запись). ---")
            return 'db_error', None
            
    except Exception as e:
        logger.error(f"Критическая ошибка в fetch_and_cache_word_data: {e}", exc_info=True)
        return 'error', None
    finally:
        logger.info(f"Шаг 6: Очистка события для '{search_word}'.")
        async with PARSING_EVENTS_LOCK:
            if normalized_search_word in PARSING_EVENTS:
                PARSING_EVENTS[normalized_search_word].set()
                del PARSING_EVENTS[normalized_search_word]