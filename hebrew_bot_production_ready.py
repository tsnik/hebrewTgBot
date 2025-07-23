# -*- coding: utf-8 -*-

"""
Telegram-бот "Помощник по ивриту"
Версия: 14.6 (Восстановлена логика из v13.1)
Дата обновления: 24 июля 2025 г.

Ключевые изменения в этой версии:
- REVERT: Восстановлена полная версия функции `normalize_hebrew` с логикой
  приведения к базовой форме, как в v13.1.
- REFACTOR: В функцию `display_word_card` возвращен параметр `in_dictionary`
  для более явного управления состоянием.
- REVERT: Восстановлен детальный пошаговый стиль логирования внутри
  `fetch_and_cache_word_data` для максимальной информативности.
- REFACTOR: Улучшен парсер существительных (`parse_noun_or_adjective_page`).
"""

import logging
import sqlite3
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup, Tag
import re
import os
import sys
from dotenv import load_dotenv
import queue
import threading
import time
from urllib.parse import quote, urljoin
from typing import Tuple, Dict, Any, List, Optional, Callable
from collections.abc import Callable as CallableABC
import asyncio

# --- ИМПОРТЫ TELEGRAM ---
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode


# --- КОНФИГУРАЦИЯ И КОНСТАНТЫ ---
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip().strip("'\"")
DB_NAME = "data/hebrew_helper_cache.db"

# Настройки парсера и БД
PARSING_TIMEOUT = 15
DB_READ_ATTEMPTS = 5
DB_READ_DELAY = 0.2
CONVERSATION_TIMEOUT_SECONDS = 1800 # 30 минут
VERB_TRAINER_RETRY_ATTEMPTS = 3

# Настройка логирования
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ПОТОКОБЕЗОПАСНОСТЬ И БЛОКИРОВКИ ---
DB_WRITE_QUEUE = queue.Queue()
PARSING_EVENTS = {}
PARSING_EVENTS_LOCK = threading.Lock()


# --- НОРМАЛИЗАЦИЯ ИВРИТА И ПАРСИНГ ПЕРЕВОДОВ ---

def normalize_hebrew(text: str) -> str:
    """
    Нормализует текст на иврите: удаляет огласовки (никуд) и
    приводит к базовой форме написания.
    """
    if not text:
        return ""
    # Удаление всех огласовок (U+0591 до U+05C7)
    text = re.sub(r'[\u0591-\u05C7]', '', text)
    # Базовые правила унификации (можно расширять)
    # text = text.replace('יי', 'י')
    # text = text.replace('וו', 'ו')
    return text.strip()

def parse_translations(raw_text: str) -> List[Dict[str, Any]]:
    """
    Принимает сырую строку из div.lead и преобразует ее в
    структурированный список переводов.
    """
    all_translations = []
    if not raw_text:
        return []

    major_groups = [group.strip() for group in raw_text.split(';')]

    for group_text in major_groups:
        comment_match = re.search(r'\((.*?)\)', group_text)
        comment = comment_match.group(1).strip() if comment_match else None
        
        clean_group_text = re.sub(r'\s*\((.*?)\)', '', group_text).strip()

        minor_translations = [t.strip() for t in clean_group_text.split(',')]

        for translation_text in minor_translations:
            if translation_text:
                all_translations.append({
                    'translation_text': translation_text,
                    'context_comment': comment,
                    'is_primary': False
                })

    if all_translations:
        all_translations[0]['is_primary'] = True

    return all_translations


# --- УПРАВЛЕНИЕ БАЗОЙ ДАННЫХ ---

def db_worker():
    """Worker, который последовательно выполняет запросы на запись в БД."""
    os.makedirs(os.path.dirname(DB_NAME), exist_ok=True)
    conn = sqlite3.connect(DB_NAME, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    while True:
        try:
            item = DB_WRITE_QUEUE.get()
            if item is None: break
            cursor = conn.cursor()
            if isinstance(item, CallableABC):
                try:
                    cursor.execute("BEGIN TRANSACTION")
                    item(cursor)
                    conn.commit()
                except Exception as e:
                    logger.error(f"DB-WORKER: Ошибка в транзакционной функции, откатываем. Ошибка: {e}", exc_info=True)
                    conn.rollback()
            else:
                query, params, is_many = item
                if is_many: cursor.executemany(query, params)
                else: cursor.execute(query, params)
                conn.commit()
        except Exception as e:
            logger.error(f"DB-WORKER: Критическая ошибка: {e}", exc_info=True)

def db_write_query(query, params=(), many=False):
    DB_WRITE_QUEUE.put((query, params, many))

def db_transaction(func: Callable[[sqlite3.Cursor], None]):
    DB_WRITE_QUEUE.put(func)

def db_read_query(query, params=(), fetchone=False, fetchall=False):
    try:
        conn = sqlite3.connect(DB_NAME, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params)
        result = None
        if fetchone: result = cursor.fetchone()
        if fetchall: result = cursor.fetchall()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"DB-READ: Ошибка: {e}")
        return None

def init_db():
    """Инициализирует БД в соответствии с требованиями v14."""
    db_write_query("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT)")
    db_write_query("""
        CREATE TABLE IF NOT EXISTS cached_words (
            word_id INTEGER PRIMARY KEY AUTOINCREMENT,
            hebrew TEXT NOT NULL UNIQUE,
            normalized_hebrew TEXT NOT NULL,
            transcription TEXT,
            is_verb BOOLEAN,
            root TEXT,
            binyan TEXT,
            fetched_at TIMESTAMP
        )
    """)
    db_write_query("""
        CREATE TABLE IF NOT EXISTS translations (
            translation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_id INTEGER,
            translation_text TEXT NOT NULL,
            context_comment TEXT,
            is_primary BOOLEAN NOT NULL,
            FOREIGN KEY (word_id) REFERENCES cached_words (word_id) ON DELETE CASCADE
        )
    """)
    db_write_query("""
        CREATE TABLE IF NOT EXISTS user_dictionary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            word_id INTEGER,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            srs_level INTEGER DEFAULT 0,
            next_review_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (word_id) REFERENCES cached_words (word_id) ON DELETE CASCADE,
            UNIQUE(user_id, word_id)
        )
    """)
    db_write_query("""
        CREATE TABLE IF NOT EXISTS verb_conjugations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_id INTEGER,
            tense TEXT,
            person TEXT,
            hebrew_form TEXT NOT NULL,
            normalized_hebrew_form TEXT NOT NULL,
            transcription TEXT,
            FOREIGN KEY (word_id) REFERENCES cached_words (word_id) ON DELETE CASCADE
        )
    """)
    db_write_query("CREATE INDEX IF NOT EXISTS idx_normalized_hebrew ON cached_words(normalized_hebrew)")
    db_write_query("CREATE INDEX IF NOT EXISTS idx_normalized_hebrew_form ON verb_conjugations(normalized_hebrew_form)")
    db_write_query("CREATE INDEX IF NOT EXISTS idx_translations_word_id ON translations(word_id)")


# --- МОДУЛЬНАЯ АРХИТЕКТУРА ПАРСЕРА ---

def local_search(normalized_search_word: str) -> Optional[Dict[str, Any]]:
    """Ищет слово в локальной базе данных по НОРМАЛИЗОВАННОЙ форме."""
    word_id = None
    conjugation = db_read_query("SELECT word_id FROM verb_conjugations WHERE normalized_hebrew_form = ?", (normalized_search_word,), fetchone=True)
    if conjugation:
        word_id = conjugation['word_id']
    else:
        word_data_row = db_read_query("SELECT word_id FROM cached_words WHERE normalized_hebrew = ?", (normalized_search_word,), fetchone=True)
        if word_data_row:
            word_id = word_data_row['word_id']

    if not word_id:
        return None

    word_data = db_read_query("SELECT * FROM cached_words WHERE word_id = ?", (word_id,), fetchone=True)
    if not word_data:
        return None
    
    translations = db_read_query("SELECT * FROM translations WHERE word_id = ? ORDER BY is_primary DESC", (word_id,), fetchall=True)
    
    result = dict(word_data)
    result['translations'] = [dict(t) for t in translations]
    return result

def parse_verb_page(soup: BeautifulSoup, main_header: Tag) -> Optional[Dict[str, Any]]:
    """Парсер для страниц глаголов с детальным логированием."""
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
            if 'глагол' in p.text.lower() and p.find('b'): data['binyan'] = p.find('b').text.strip()
            if 'корень' in p.text.lower() and p.find('span', class_='menukad'): data['root'] = p.find('span', class_='menukad').text.strip()

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
        logger.error(f"Критическая ошибка в parse_verb_page: {e}", exc_info=True)
        return None

def parse_noun_or_adjective_page(soup: BeautifulSoup, main_header: Tag) -> Optional[Dict[str, Any]]:
    """Парсер для страниц существительных и прилагательных с улучшенной логикой."""
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
            logger.error("--> parse_noun_or_adjective_page: не удалось найти каноническую форму ни одним из методов.")
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
        logger.error(f"Критическая ошибка в parse_noun_or_adjective_page: {e}", exc_info=True)
        return None

def fetch_and_cache_word_data(search_word: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Функция-диспетчер парсинга с детальным логированием."""
    is_owner = False
    normalized_search_word = normalize_hebrew(search_word)
    with PARSING_EVENTS_LOCK:
        if normalized_search_word not in PARSING_EVENTS:
            PARSING_EVENTS[normalized_search_word] = threading.Event()
            is_owner = True
        event = PARSING_EVENTS[normalized_search_word]

    if not is_owner:
        logger.info(f"Парсинг для '{search_word}' уже запущен, ожидание...")
        event.wait(timeout=PARSING_TIMEOUT)
        result = local_search(normalized_search_word)
        return ('ok', result) if result else ('not_found', None)

    try:
        logger.info(f"--- Начало парсинга для '{search_word}' ---")
        logger.info("Шаг 1: Выполнение HTTP-запроса...")
        try:
            search_url = f"https://www.pealim.com/ru/search/?q={quote(search_word)}"
            session = requests.Session()
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'}
            session.headers.update(headers)
            search_response = session.get(search_url, timeout=10)
            search_response.raise_for_status()
            logger.info(f"Шаг 1.1: Успешно получен ответ от {search_url}")
            
            if "/dict/" in search_response.url:
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
                final_url = urljoin(search_response.url, result_link['href'])
                logger.info(f"Шаг 1.3: Найдена ссылка, переход на {final_url}")
                response = session.get(final_url, timeout=10)
                response.raise_for_status()
        except requests.RequestException as e:
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
            logger.error("Парсинг не удался: одна из функций (parse_verb_page/parse_noun_or_adjective_page) вернула None.")
            return 'error', None
        
        logger.info(f"Шаг 3: Обработка и НОРМАЛИЗАЦИЯ результата парсинга для '{parsed_data['hebrew']}'...")
        parsed_data['normalized_hebrew'] = normalize_hebrew(parsed_data['hebrew'])
        if parsed_data.get('conjugations'):
            for conj in parsed_data['conjugations']:
                conj['normalized_hebrew_form'] = normalize_hebrew(conj['hebrew_form'])
        
        if local_search(parsed_data['normalized_hebrew']):
             logger.info(f"Шаг 3.2: Нормализованная форма '{parsed_data['normalized_hebrew']}' уже есть в кэше. Сохранение не требуется.")
             return 'ok', local_search(parsed_data['normalized_hebrew'])

        logger.info(f"Шаг 4: Сохранение '{parsed_data['hebrew']}' и его нормализованных форм в БД...")
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
                translations_to_insert = [
                    (word_id, t['translation_text'], t['context_comment'], t['is_primary'])
                    for t in parsed_data['translations']
                ]
                cursor.executemany("""
                    INSERT INTO translations (word_id, translation_text, context_comment, is_primary)
                    VALUES (?, ?, ?, ?)
                """, translations_to_insert)

            if word_id and parsed_data.get('conjugations'):
                conjugations_to_insert = [
                    (word_id, c['tense'], c['person'], c['hebrew_form'], c['normalized_hebrew_form'], c['transcription'])
                    for c in parsed_data['conjugations']
                ]
                cursor.executemany("""
                    INSERT INTO verb_conjugations (word_id, tense, person, hebrew_form, normalized_hebrew_form, transcription)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, conjugations_to_insert)
        db_transaction(_save_word_transaction)
        
        logger.info("Шаг 5: Ожидание появления слова в БД и возврат результата...")
        final_word_data = None
        for i in range(DB_READ_ATTEMPTS):
            final_word_data = local_search(parsed_data['normalized_hebrew'])
            if final_word_data: break
            time.sleep(DB_READ_DELAY)
        
        if final_word_data:
            logger.info(f"--- Парсинг для '{search_word}' завершен УСПЕШНО. ---")
            return ('ok', final_word_data)
        else:
            logger.error(f"--- Парсинг для '{search_word}' завершен с ОШИБКОЙ БД (не удалось прочитать запись). ---")
            return ('db_error', None)
            
    except Exception as e:
        logger.error(f"Критическая ошибка в fetch_and_cache_word_data: {e}", exc_info=True)
        return 'error', None
    finally:
        logger.info(f"Шаг 6: Очистка для '{search_word}'.")
        with PARSING_EVENTS_LOCK:
            if normalized_search_word in PARSING_EVENTS:
                PARSING_EVENTS[normalized_search_word].set()
                del PARSING_EVENTS[normalized_search_word]

# --- КОЛЛБЭК-ДАННЫЕ И СОСТОЯНИЯ ---
TRAINING_MENU_STATE, FLASHCARD_SHOW, FLASHCARD_EVAL, AWAITING_VERB_ANSWER, VERB_TRAINER_NEXT_ACTION = range(5)
CB_DICT_VIEW, CB_DICT_DELETE_MODE, CB_DICT_CONFIRM_DELETE, CB_DICT_EXECUTE_DELETE = "d_v", "d_dm", "d_cd", "d_ed"
CB_ADD, CB_SHOW_VERB, CB_VIEW_CARD = "add", "sh_v", "v_c"
CB_TRAIN_MENU, CB_TRAIN_HE_RU, CB_TRAIN_RU_HE, CB_VERB_TRAINER_START = "t_m", "t_hr", "t_rh", "vts"
CB_SHOW_ANSWER, CB_EVAL_CORRECT, CB_EVAL_INCORRECT, CB_END_TRAINING = "sh_a", "e_c", "e_i", "e_t"

# --- ОСНОВНЫЕ ХЕНДЛЕРЫ ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_write_query("INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?, ?, ?)", (user.id, user.first_name, user.username))
    keyboard = [[InlineKeyboardButton("🧠 Мой словарь", callback_data=f"{CB_DICT_VIEW}_0")], [InlineKeyboardButton("💪 Тренировка", callback_data=CB_TRAIN_MENU)]]
    await update.message.reply_text(f"Привет, {user.first_name}! Отправь мне слово на иврите для поиска.", reply_markup=InlineKeyboardMarkup(keyboard))

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🧠 Мой словарь", callback_data=f"{CB_DICT_VIEW}_0")], [InlineKeyboardButton("💪 Тренировка", callback_data=CB_TRAIN_MENU)]]
    await query.edit_message_text("Главное меню:", reply_markup=InlineKeyboardMarkup(keyboard))

async def display_word_card(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    word_data: dict,
    message_id: Optional[int] = None,
    in_dictionary: Optional[bool] = None
):
    """Отображает карточку слова с множественными переводами."""
    word_id = word_data['word_id']
    
    if in_dictionary is None:
        in_dictionary = db_read_query("SELECT 1 FROM user_dictionary WHERE user_id = ? AND word_id = ?", (user_id, word_id), fetchone=True)
    
    translations = word_data.get('translations', [])
    primary_translation = next((t['translation_text'] for t in translations if t['is_primary']), "Перевод не найден")
    other_translations = [t['translation_text'] for t in translations if not t['is_primary']]
    
    translation_str = primary_translation
    if other_translations:
        translation_str += f" (также: {', '.join(other_translations)})"

    card_text_header = f"Слово *{word_data['hebrew']}* уже в вашем словаре." if in_dictionary else f"Найдено: *{word_data['hebrew']}*"
    card_text = f"{card_text_header} [{word_data.get('transcription', '')}]\nПеревод: {translation_str}"

    keyboard_buttons = []
    if in_dictionary:
        keyboard_buttons.append(InlineKeyboardButton("🗑️ Удалить", callback_data=f"{CB_DICT_CONFIRM_DELETE}_{word_id}_0"))
    else:
        keyboard_buttons.append(InlineKeyboardButton("➕ Добавить", callback_data=f"{CB_ADD}_{word_id}"))

    if word_data.get('is_verb'):
        keyboard_buttons.append(InlineKeyboardButton("📖 Спряжения", callback_data=f"{CB_SHOW_VERB}_{word_id}"))

    keyboard = [keyboard_buttons, [InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if message_id:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=card_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        else:
            await context.bot.send_message(chat_id=chat_id, text=card_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Ошибка при отправке/редактировании карточки слова: {e}", exc_info=True)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    text = update.message.text.strip()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not re.match(r'^[\u0590-\u05FF\s-]+$', text):
        await update.message.reply_text("Пожалуйста, используйте только буквы иврита.")
        return

    normalized_text = normalize_hebrew(text)
    word_data = local_search(normalized_text)

    if word_data:
        await display_word_card(context, user_id, chat_id, word_data)
        return

    status_message = await update.message.reply_text("🔎 Ищу слово во внешнем словаре...")
    status, data = await asyncio.to_thread(fetch_and_cache_word_data, text)

    if status == 'ok' and data:
        await display_word_card(context, user_id, chat_id, data, message_id=status_message.message_id)
    elif status == 'not_found':
        await context.bot.edit_message_text(f"Слово '{text}' не найдено.", chat_id=chat_id, message_id=status_message.message_id)
    else:
        await context.bot.edit_message_text(
            "Произошла внутренняя ошибка при поиске слова. "
            "Если проблема повторится, пожалуйста, сообщите администратору.",
            chat_id=chat_id, message_id=status_message.message_id
        )

async def add_word_to_dictionary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    word_id = int(query.data.split('_')[1])
    user_id = query.from_user.id
    
    db_write_query("INSERT OR IGNORE INTO user_dictionary (user_id, word_id, next_review_at) VALUES (?, ?, ?)", (user_id, word_id, datetime.now()))
    
    await query.answer("Добавлено!")

    word_data_row = db_read_query("SELECT normalized_hebrew FROM cached_words WHERE word_id = ?", (word_id,), fetchone=True)
    if word_data_row:
        word_data = local_search(word_data_row['normalized_hebrew'])
        if word_data:
            await display_word_card(context, user_id, query.message.chat_id, word_data, message_id=query.message.message_id, in_dictionary=True)

async def view_dictionary_page_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split('_')
    page = int(parts[-1])
    deletion_mode = parts[1] == "dm"
    await view_dictionary_page_logic(update, context, page=page, deletion_mode=deletion_mode)

async def view_dictionary_page_logic(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, deletion_mode: bool, exclude_word_id: Optional[int] = None):
    query = update.callback_query
    user_id = query.from_user.id
    
    sql_query = """
        SELECT cw.word_id, cw.hebrew, t.translation_text
        FROM cached_words cw
        JOIN user_dictionary ud ON cw.word_id = ud.word_id
        JOIN translations t ON cw.word_id = t.word_id
        WHERE ud.user_id = ? AND t.is_primary = 1
        ORDER BY ud.added_at DESC LIMIT 6 OFFSET ?
    """
    words_from_db = db_read_query(sql_query, (user_id, page * 5), fetchall=True)
    
    words = [w for w in words_from_db if w['word_id'] != exclude_word_id] if exclude_word_id else words_from_db
    
    has_next_page = len(words) > 5
    words = words[:5]

    if not words and page > 0:
        return await view_dictionary_page_logic(update, context, page=page - 1, deletion_mode=False)
    if not words and page == 0:
        await query.edit_message_text("Ваш словарь пуст.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu")]]))
        return

    keyboard, message_text = [], "Ваш словарь (стр. {}):\n\n".format(page + 1)
    if deletion_mode: message_text = "Выберите слово для удаления:"
    for word in words:
        if deletion_mode:
            keyboard.append([InlineKeyboardButton(f"🗑️ {word['hebrew']}", callback_data=f"{CB_DICT_CONFIRM_DELETE}_{word['word_id']}_{page}")])
        else:
            message_text += f"• {word['hebrew']} — {word['translation_text']}\n"
    
    nav_buttons = []
    nav_pattern = CB_DICT_DELETE_MODE if deletion_mode else CB_DICT_VIEW
    if page > 0: nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"{nav_pattern}_{page-1}"))
    if has_next_page: nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"{nav_pattern}_{page+1}"))
    if nav_buttons: keyboard.append(nav_buttons)
    
    if deletion_mode:
        keyboard.append([InlineKeyboardButton("⬅️ К словарю", callback_data=f"{CB_DICT_VIEW}_{page}")])
    else:
        keyboard.append([InlineKeyboardButton("🗑️ Удалить слово", callback_data=f"{CB_DICT_DELETE_MODE}_0")])
        keyboard.append([InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu")])
    
    await query.edit_message_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def confirm_delete_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, _, word_id_str, page_str = query.data.split('_')
    word_data = db_read_query("SELECT hebrew FROM cached_words WHERE word_id = ?", (word_id_str,), fetchone=True)
    if not word_data:
        await query.edit_message_text("Ошибка: слово не найдено.")
        return
    text = f"Удалить слово '{word_data['hebrew']}'?"
    keyboard = [[InlineKeyboardButton("✅ Да", callback_data=f"{CB_DICT_EXECUTE_DELETE}_{word_id_str}_{page_str}")], [InlineKeyboardButton("❌ Нет", callback_data=f"{CB_DICT_DELETE_MODE}_{page_str}")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def execute_delete_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Слово удалено")
    _, _, word_id_str, page_str = query.data.split('_')
    word_id, page = int(word_id_str), int(page_str)
    
    db_write_query("DELETE FROM user_dictionary WHERE user_id = ? AND word_id = ?", (query.from_user.id, word_id))
    
    await view_dictionary_page_logic(update, context, page=page, deletion_mode=False, exclude_word_id=word_id)

async def training_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query: 
        await query.answer()
        await query.edit_message_text(
            "Выберите режим тренировки:", 
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🇮🇱 → 🇷🇺", callback_data=CB_TRAIN_HE_RU)], 
                [InlineKeyboardButton("🇷🇺 → 🇮🇱", callback_data=CB_TRAIN_RU_HE)], 
                [InlineKeyboardButton("🔥 Глаголы", callback_data=CB_VERB_TRAINER_START)], 
                [InlineKeyboardButton("⬅️ В меню", callback_data="main_menu")]
            ])
        )
    return TRAINING_MENU_STATE

async def start_flashcard_training(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['training_mode'] = query.data
    
    sql_query = """
        SELECT cw.*, t.translation_text
        FROM cached_words cw
        JOIN user_dictionary ud ON cw.word_id = ud.word_id
        JOIN translations t ON cw.word_id = t.word_id
        WHERE ud.user_id = ? AND cw.is_verb = 0 AND t.is_primary = 1
        ORDER BY ud.next_review_at ASC LIMIT 10
    """
    words = db_read_query(sql_query, (query.from_user.id,), fetchall=True)

    if not words:
        await query.edit_message_text("В словаре нет слов для тренировки.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=CB_TRAIN_MENU)]]))
        return ConversationHandler.END
    context.user_data.update({'words': [dict(w) for w in words], 'idx': 0, 'correct': 0})
    return await show_next_card(update, context)

async def show_next_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query: await query.answer()
    idx, words = context.user_data['idx'], context.user_data['words']
    if idx >= len(words):
        await query.edit_message_text(f"Результат: {context.user_data['correct']}/{len(words)}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💪 Еще", callback_data=context.user_data['training_mode'])], [InlineKeyboardButton("⬅️ В меню", callback_data=CB_TRAIN_MENU)]]))
        return ConversationHandler.END
    word = words[idx]
    question = word['hebrew'] if context.user_data['training_mode'] == CB_TRAIN_HE_RU else word['translation_text']
    keyboard = [[InlineKeyboardButton("💡 Ответ", callback_data=CB_SHOW_ANSWER)], [InlineKeyboardButton("❌ Закончить", callback_data=CB_END_TRAINING)]]
    
    message_text = f"Слово {idx+1}/{len(words)}:\n\n*{question}*"
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    
    return FLASHCARD_SHOW

async def show_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    word = context.user_data['words'][context.user_data['idx']]
    answer_text = f"*{word['hebrew']}* [{word['transcription']}]\nПеревод: {word['translation_text']}"
    keyboard = [[InlineKeyboardButton("✅ Знаю", callback_data=CB_EVAL_CORRECT)], [InlineKeyboardButton("❌ Не знаю", callback_data=CB_EVAL_INCORRECT)]]
    await query.edit_message_text(answer_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return FLASHCARD_EVAL

async def handle_self_evaluation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    word = context.user_data['words'][context.user_data['idx']]
    srs_data = db_read_query("SELECT srs_level FROM user_dictionary WHERE user_id = ? AND word_id = ?", (query.from_user.id, word['word_id']), fetchone=True)
    srs_level = srs_data['srs_level'] if srs_data else 0
    if query.data == CB_EVAL_CORRECT:
        context.user_data['correct'] += 1
        srs_level += 1
    else: srs_level = 0
    next_review_date = datetime.now() + timedelta(days=[0, 1, 3, 7, 14, 30, 90][min(srs_level, 6)])
    db_write_query("UPDATE user_dictionary SET srs_level = ?, next_review_at = ? WHERE user_id = ? AND word_id = ?", (srs_level, next_review_date, query.from_user.id, word['word_id']))
    context.user_data['idx'] += 1
    return await show_next_card(update, context)

async def start_verb_trainer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    verb, conjugation = None, None

    for i in range(VERB_TRAINER_RETRY_ATTEMPTS):
        verb_candidate = db_read_query("SELECT cw.* FROM cached_words cw JOIN user_dictionary ud ON cw.word_id = ud.word_id WHERE ud.user_id = ? AND cw.is_verb = 1 ORDER BY RANDOM() LIMIT 1", (user_id,), fetchone=True)
        if not verb_candidate:
            await query.edit_message_text("В вашем словаре нет глаголов для тренировки.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=CB_TRAIN_MENU)]]))
            return TRAINING_MENU_STATE

        conjugation_candidate = db_read_query("SELECT * FROM verb_conjugations WHERE word_id = ? ORDER BY RANDOM() LIMIT 1", (verb_candidate['word_id'],), fetchone=True)
        if conjugation_candidate:
            verb, conjugation = verb_candidate, conjugation_candidate
            break
        else:
            logger.warning(f"Ошибка целостности данных: у глагола {verb_candidate['hebrew']} (id: {verb_candidate['word_id']}) нет спряжений.")

    if not verb or not conjugation:
        await query.edit_message_text("Возникла проблема с данными для тренировки.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=CB_TRAIN_MENU)]]))
        return TRAINING_MENU_STATE

    context.user_data['answer'] = dict(conjugation)
    context.user_data['answer']['normalized_hebrew_form'] = normalize_hebrew(conjugation['hebrew_form'])
    
    await query.edit_message_text(f"Глагол: *{verb['hebrew']}*\nНапишите форму для: *{conjugation['tense']}, {conjugation['person']}*", parse_mode=ParseMode.MARKDOWN)
    return AWAITING_VERB_ANSWER

async def check_verb_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    correct = context.user_data['answer']
    
    normalized_user_answer = normalize_hebrew(update.message.text)
    correct_normalized_form = correct['normalized_hebrew_form']

    if normalized_user_answer == correct_normalized_form:
        await update.message.reply_text(f"✅ Верно! *{correct['hebrew_form']}*", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"❌ Неверно. Правильно: *{correct['hebrew_form']}*", parse_mode=ParseMode.MARKDOWN)
    
    db_write_query("UPDATE user_dictionary SET next_review_at = ? WHERE user_id = ? AND word_id = ?", (datetime.now() + timedelta(days=1), update.effective_user.id, correct['word_id']))
    
    keyboard = [[InlineKeyboardButton("🔥 Продолжить", callback_data=CB_VERB_TRAINER_START)], [InlineKeyboardButton("⬅️ В меню", callback_data=CB_TRAIN_MENU)]]
    await update.message.reply_text("Что дальше?", reply_markup=InlineKeyboardMarkup(keyboard))
    
    return VERB_TRAINER_NEXT_ACTION

async def end_training(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Тренировка прервана.")
    await training_menu(update, context)
    return ConversationHandler.END

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await main_menu(update, context)
    return ConversationHandler.END

async def show_verb_conjugations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    word_id = int(query.data.split('_')[-1])
    word_info = db_read_query("SELECT hebrew FROM cached_words WHERE word_id = ?", (word_id,), fetchone=True)
    conjugations_raw = db_read_query("SELECT tense, person, hebrew_form, transcription FROM verb_conjugations WHERE word_id = ? ORDER BY id", (word_id,), fetchall=True)
    
    keyboard = [[InlineKeyboardButton("⬅️ Назад к слову", callback_data=f"{CB_VIEW_CARD}_{word_id}")]]

    if not conjugations_raw or not word_info:
        await query.edit_message_text("Для этого глагола нет таблицы спряжений.", reply_markup=InlineKeyboardMarkup(keyboard))
        return
        
    conjugations_by_tense = {}
    message_text = f"Спряжения для *{word_info['hebrew']}*:\n"
    
    for conj in conjugations_raw:
        if conj['tense'] not in conjugations_by_tense: conjugations_by_tense[conj['tense']] = []
        conjugations_by_tense[conj['tense']].append(conj)
        
    for tense, conjugations in conjugations_by_tense.items():
        message_text += f"\n*{tense.capitalize()}*:\n"
        for conj in conjugations: message_text += f"_{conj['person']}_: {conj['hebrew_form']} ({conj['transcription']})\n"
            
    if len(message_text) > 4096: message_text = message_text[:4090] + "\n(...)"
    
    await query.edit_message_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def view_word_card_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    word_id = int(query.data.split('_')[-1])
    user_id = query.from_user.id
    
    word_data_row = db_read_query("SELECT normalized_hebrew FROM cached_words WHERE word_id = ?", (word_id,), fetchone=True)
    if word_data_row:
        word_data = local_search(word_data_row['normalized_hebrew'])
        if word_data:
            await display_word_card(context, user_id, query.message.chat_id, word_data, message_id=query.message.message_id)
    else:
        await query.edit_message_text("Ошибка: слово не найдено.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu")]]))


def main() -> None:
    if not BOT_TOKEN:
        logger.critical("Токен не найден. Укажите TELEGRAM_BOT_TOKEN в .env файле.")
        sys.exit("Токен не найден.")

    db_worker_thread = threading.Thread(target=db_worker, daemon=True)
    db_worker_thread.start()
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()

    conv_defaults = {"per_user": True, "per_chat": True, "conversation_timeout": CONVERSATION_TIMEOUT_SECONDS}

    training_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(training_menu, pattern=f"^{CB_TRAIN_MENU}$")],
        states={
            TRAINING_MENU_STATE: [
                CallbackQueryHandler(start_flashcard_training, pattern=f"^({CB_TRAIN_HE_RU}|{CB_TRAIN_RU_HE})$"),
                CallbackQueryHandler(start_verb_trainer, pattern=f"^{CB_VERB_TRAINER_START}$"),
                CallbackQueryHandler(back_to_main_menu, pattern="^main_menu$")
            ],
            FLASHCARD_SHOW: [
                CallbackQueryHandler(show_answer, pattern=f"^{CB_SHOW_ANSWER}$"),
                CallbackQueryHandler(end_training, pattern=f"^{CB_END_TRAINING}$")
            ],
            FLASHCARD_EVAL: [
                CallbackQueryHandler(handle_self_evaluation, pattern=f"^{CB_EVAL_CORRECT}|{CB_EVAL_INCORRECT}$")
            ],
            AWAITING_VERB_ANSWER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, check_verb_answer)
            ],
            VERB_TRAINER_NEXT_ACTION: [
                CallbackQueryHandler(start_verb_trainer, pattern=f"^{CB_VERB_TRAINER_START}$"),
                CallbackQueryHandler(training_menu, pattern=f"^{CB_TRAIN_MENU}$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(end_training, pattern=f"^{CB_END_TRAINING}$"),
            CallbackQueryHandler(back_to_main_menu, pattern="^main_menu$"),
        ],
        map_to_parent={
            ConversationHandler.END: TRAINING_MENU_STATE
        },
        **conv_defaults
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(view_dictionary_page_handler, pattern=f"^{CB_DICT_VIEW}_|{CB_DICT_DELETE_MODE}_"))
    application.add_handler(CallbackQueryHandler(confirm_delete_word, pattern=f"^{CB_DICT_CONFIRM_DELETE}_"))
    application.add_handler(CallbackQueryHandler(execute_delete_word, pattern=f"^{CB_DICT_EXECUTE_DELETE}_"))
    application.add_handler(CallbackQueryHandler(add_word_to_dictionary, pattern=f"^{CB_ADD}_"))
    application.add_handler(CallbackQueryHandler(show_verb_conjugations, pattern=f"^{CB_SHOW_VERB}_"))
    application.add_handler(CallbackQueryHandler(view_word_card_handler, pattern=f"^{CB_VIEW_CARD}_"))
    application.add_handler(training_conv)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logger.info("Бот запускается...")
    application.run_polling()
    
    DB_WRITE_QUEUE.put(None)
    db_worker_thread.join()

if __name__ == "__main__":
    main()
