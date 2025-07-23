# -*- coding: utf-8 -*-

"""
Telegram-бот "Помощник по ивриту"
Версия: 12.5 (Восстановлено детальное логирование)
Дата обновления: 23 июля 2025 г.

Ключевые изменения в этой версии:
- DEBUG: Восстановлено подробное пошаговое логирование в модуле парсера
  для облегчения отладки, как было в первоначальной версии.
- CRITICAL FIX: Исправлена основная проблема, из-за которой бот не отвечал
  карточкой слова после первого парсинга. Это было вызвано потерей
  контекста после длительной операции в потоке. Теперь для всех
  действий после `await` используется `context.bot` с явным указанием
  `chat_id` и `message_id`, что является надежным подходом.
- REFACTOR: Функция `display_word_card` и ее вызовы были переработаны
  для использования `context.bot`, что повысило стабильность кода.
- FIX: Добавлен UNIQUE constraint в таблицу user_dictionary для атомарного
  предотвращения "двойного добавления" слов (race condition).
- PERF: Включен режим WAL для SQLite для улучшения параллелизма
  при операциях чтения и записи в БД.
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

# --- УПРАВЛЕНИЕ БАЗОЙ ДАННЫХ (С ПОДДЕРЖКОЙ ТРАНЗАКЦИЙ) ---

def db_worker():
    """
    Worker, который последовательно выполняет запросы на запись в БД.
    """
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
    """Помещает одиночный запрос на запись в очередь."""
    DB_WRITE_QUEUE.put((query, params, many))

def db_transaction(func: Callable[[sqlite3.Cursor], None]):
    """Помещает функцию для выполнения внутри транзакции."""
    DB_WRITE_QUEUE.put(func)

def db_read_query(query, params=(), fetchone=False, fetchall=False):
    """Выполняет запрос на чтение и возвращает результат."""
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
    """Инициализирует БД."""
    db_write_query("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT)")
    db_write_query("CREATE TABLE IF NOT EXISTS cached_words (word_id INTEGER PRIMARY KEY AUTOINCREMENT, hebrew TEXT NOT NULL UNIQUE, translation TEXT NOT NULL, transcription TEXT, is_verb BOOLEAN, root TEXT, binyan TEXT, fetched_at TIMESTAMP)")
    db_write_query("""
        CREATE TABLE IF NOT EXISTS user_dictionary (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            user_id INTEGER, 
            word_id INTEGER, 
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
            srs_level INTEGER DEFAULT 0, 
            next_review_at TIMESTAMP, 
            FOREIGN KEY (user_id) REFERENCES users (user_id), 
            FOREIGN KEY (word_id) REFERENCES cached_words (word_id),
            UNIQUE(user_id, word_id) 
        )
    """)
    db_write_query("CREATE TABLE IF NOT EXISTS verb_conjugations (id INTEGER PRIMARY KEY AUTOINCREMENT, word_id INTEGER, tense TEXT, person TEXT, hebrew_form TEXT NOT NULL, transcription TEXT, FOREIGN KEY (word_id) REFERENCES cached_words (word_id))")
    db_write_query("CREATE INDEX IF NOT EXISTS idx_hebrew_form ON verb_conjugations(hebrew_form)")


# --- МОДУЛЬНАЯ АРХИТЕКТУРА ПАРСЕРА ---

def local_search(search_word: str) -> Optional[Dict[str, Any]]:
    """Ищет слово в локальной базе данных."""
    conjugation = db_read_query("SELECT word_id FROM verb_conjugations WHERE hebrew_form = ?", (search_word,), fetchone=True)
    if conjugation:
        word_data = db_read_query("SELECT * FROM cached_words WHERE word_id = ?", (conjugation['word_id'],), fetchone=True)
        if word_data:
            return dict(word_data)

    word_data = db_read_query("SELECT * FROM cached_words WHERE hebrew = ?", (search_word,), fetchone=True)
    if word_data:
        return dict(word_data)

    return None

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
        
        logger.info("--> parse_verb_page: Поиск перевода и транскрипции...")
        data['translation'] = soup.find('div', class_='lead').text.strip()
        data['transcription'] = infinitive_div.find('div', class_='transcription').text.strip()
        
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
            potential_word = soup.title.string.split('–')[0].strip()
            if re.match(r'^[\u0590-\u05FF\s-]+$', potential_word):
                canonical_hebrew = potential_word
        
        if not canonical_hebrew: 
            logger.error("--> parse_noun_or_adjective_page: Не удалось найти каноническую форму.")
            return None
        data['hebrew'] = canonical_hebrew
        logger.info(f"--> parse_noun_or_adjective_page: Каноническая форма найдена: {data['hebrew']}")
        
        logger.info("--> parse_noun_or_adjective_page: Поиск перевода и транскрипции...")
        data['translation'] = soup.find('div', class_='lead').text.strip()
        data['transcription'] = soup.find('div', class_='transcription').text.strip()
        
        logger.info("-> parse_noun_or_adjective_page завершен успешно.")
        return data
    except Exception as e:
        logger.error(f"Ошибка в parse_noun_or_adjective_page: {e}", exc_info=True)
        return None

def fetch_and_cache_word_data(search_word: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Функция-диспетчер парсинга."""
    is_owner = False
    with PARSING_EVENTS_LOCK:
        if search_word not in PARSING_EVENTS:
            PARSING_EVENTS[search_word] = threading.Event()
            is_owner = True
        event = PARSING_EVENTS[search_word]

    if not is_owner:
        logger.info(f"Парсинг слова '{search_word}' уже запущен другим потоком, ожидание...")
        event.wait(timeout=PARSING_TIMEOUT)
        logger.info(f"Ожидание для '{search_word}' завершено, повторный поиск в кэше.")
        result = local_search(search_word)
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
                if not results_container: return 'not_found', None
                result_link = results_container.find('a', href=re.compile(r'/dict/'))
                if not result_link or not result_link.get('href'): return 'not_found', None
                final_url = urljoin(search_response.url, result_link['href'])
                logger.info(f"Шаг 1.3: Найдена ссылка, переход на {final_url}")
                response = session.get(final_url, timeout=10)
                response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Сетевая ошибка при запросе к pealim.com: {e}")
            return 'error', None
        
        logger.info("Шаг 1.4: Финальная страница успешно загружена.")
        soup = BeautifulSoup(response.text, 'html.parser')
        
        logger.info("Шаг 2: Определение типа страницы...")
        main_header = soup.find('h2', class_='page-header')
        if not main_header: return 'error', None

        parsed_data = None
        if "спряжение" in main_header.text.lower():
            logger.info("Шаг 2.1: Страница определена как ГЛАГОЛ.")
            parsed_data = parse_verb_page(soup, main_header)
        else:
            logger.info("Шаг 2.1: Страница определена как СУЩЕСТВИТЕЛЬНОЕ/ПРИЛАГАТЕЛЬНОЕ.")
            parsed_data = parse_noun_or_adjective_page(soup, main_header)

        logger.info("Шаг 3: Обработка результата парсинга...")
        if not parsed_data: return 'error', None
        logger.info(f"Шаг 3.1: Парсер успешно вернул данные для '{parsed_data['hebrew']}'.")
        
        if local_search(parsed_data['hebrew']):
            logger.info(f"Шаг 3.2: Каноническая форма '{parsed_data['hebrew']}' уже есть в кэше. Сохранение не требуется.")
            return 'ok', local_search(parsed_data['hebrew'])

        logger.info(f"Шаг 4: Сохранение '{parsed_data['hebrew']}' в БД...")
        def _save_word_transaction(cursor: sqlite3.Cursor):
            cursor.execute("INSERT OR IGNORE INTO cached_words (hebrew, translation, transcription, is_verb, root, binyan, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (parsed_data['hebrew'], parsed_data['translation'], parsed_data['transcription'], parsed_data['is_verb'], parsed_data['root'], parsed_data['binyan'], datetime.now()))
            word_id = cursor.lastrowid
            if word_id and parsed_data.get('conjugations'):
                conjugations_to_insert = [(word_id, c['tense'], c['person'], c['hebrew_form'], c['transcription']) for c in parsed_data['conjugations']]
                cursor.executemany("INSERT INTO verb_conjugations (word_id, tense, person, hebrew_form, transcription) VALUES (?, ?, ?, ?, ?)", conjugations_to_insert)
        db_transaction(_save_word_transaction)
        logger.info("Шаг 4.1: Транзакция на запись отправлена в очередь.")
        
        logger.info("Шаг 5: Ожидание появления слова в БД и возврат результата...")
        final_word_data = None
        for i in range(DB_READ_ATTEMPTS):
            logger.info(f"Шаг 5.{i+1}: Попытка чтения из БД...")
            final_word_data = local_search(parsed_data['hebrew'])
            if final_word_data:
                logger.info("Шаг 5.x: Слово успешно найдено в БД.")
                break
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
            if search_word in PARSING_EVENTS:
                PARSING_EVENTS[search_word].set()
                del PARSING_EVENTS[search_word]

# --- КОЛЛБЭК-ДАННЫЕ И СОСТОЯНИЯ ---
TRAINING_MENU_STATE, FLASHCARD_SHOW, FLASHCARD_EVAL, AWAITING_VERB_ANSWER = range(4)
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
    """
    Отображает карточку слова. Редактирует существующее сообщение, если
    передан message_id, иначе отправляет новое.
    """
    word_id = word_data['word_id']
    
    if in_dictionary is None:
        in_dictionary = db_read_query("SELECT 1 FROM user_dictionary WHERE user_id = ? AND word_id = ?", (user_id, word_id), fetchone=True)
    
    card_text = f"Найдено: *{word_data['hebrew']}* [{word_data.get('transcription', '')}]\nПеревод: {word_data['translation']}"
    keyboard_buttons = []
    
    if in_dictionary:
        card_text = f"Слово *{word_data['hebrew']}* уже в вашем словаре.\nПеревод: {word_data['translation']}"
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
        await update.message.reply_text("Пожалуйста, используйте только буквы иврита, пробелы и дефисы.")
        return
    if len(text.split()) > 1:
        await update.message.reply_text("Пожалуйста, отправляйте только по одному слову за раз.")
        return

    word_data = local_search(text)
    if word_data:
        await display_word_card(context, user_id, chat_id, word_data)
        return

    status_message = await update.message.reply_text("🔎 Ищу слово во внешнем словаре...")
    
    status, data = await asyncio.to_thread(fetch_and_cache_word_data, text)

    if status == 'ok' and data:
        await display_word_card(context, user_id, chat_id, data, message_id=status_message.message_id)
    elif status == 'not_found':
        await context.bot.edit_message_text(f"Слово '{text}' не найдено.", chat_id=chat_id, message_id=status_message.message_id)
    elif status == 'error':
        await context.bot.edit_message_text("Внешний сервис словаря временно недоступен. Попробуйте, пожалуйста, позже.", chat_id=chat_id, message_id=status_message.message_id)
    elif status == 'db_error':
        await context.bot.edit_message_text("Произошла внутренняя ошибка при сохранении слова. Пожалуйста, попробуйте позже.", chat_id=chat_id, message_id=status_message.message_id)

async def add_word_to_dictionary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    word_id = int(query.data.split('_')[1])
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    db_write_query("INSERT OR IGNORE INTO user_dictionary (user_id, word_id, next_review_at) VALUES (?, ?, ?)", (user_id, word_id, datetime.now()))
    
    await query.answer("Добавлено!")

    word_data = db_read_query("SELECT * FROM cached_words WHERE word_id = ?", (word_id,), fetchone=True)
    if word_data:
        await display_word_card(context, user_id, chat_id, dict(word_data), message_id=message_id, in_dictionary=True)

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
    
    words_from_db = db_read_query("SELECT cw.word_id, cw.hebrew, cw.translation FROM cached_words cw JOIN user_dictionary ud ON cw.word_id = ud.word_id WHERE ud.user_id = ? ORDER BY ud.added_at DESC LIMIT 6 OFFSET ?", (user_id, page * 5), fetchall=True)
    
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
            message_text += f"• {word['hebrew']} — {word['translation']}\n"
    
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
    if query: await query.answer()
    keyboard = [[InlineKeyboardButton("🇮🇱 → 🇷🇺", callback_data=CB_TRAIN_HE_RU)], [InlineKeyboardButton("🇷🇺 → 🇮🇱", callback_data=CB_TRAIN_RU_HE)], [InlineKeyboardButton("🔥 Глаголы", callback_data=CB_VERB_TRAINER_START)], [InlineKeyboardButton("⬅️ В меню", callback_data="main_menu")]]
    await (query.edit_message_text if query else update.message.reply_text)("Выберите режим тренировки:", reply_markup=InlineKeyboardMarkup(keyboard))
    return TRAINING_MENU_STATE

async def start_flashcard_training(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['training_mode'] = query.data
    words = db_read_query("SELECT cw.* FROM cached_words cw JOIN user_dictionary ud ON cw.word_id = ud.word_id WHERE ud.user_id = ? AND cw.is_verb = 0 ORDER BY ud.next_review_at ASC LIMIT 10", (query.from_user.id,), fetchall=True)
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
    question = word['hebrew'] if context.user_data['training_mode'] == CB_TRAIN_HE_RU else word['translation']
    keyboard = [[InlineKeyboardButton("💡 Ответ", callback_data=CB_SHOW_ANSWER)], [InlineKeyboardButton("❌ Закончить", callback_data=CB_END_TRAINING)]]
    
    message_text = f"Слово {idx+1}/{len(words)}:\n\n*{question}*"
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else: # Should not happen in this flow, but as a fallback
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

    return FLASHCARD_SHOW

async def show_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    word = context.user_data['words'][context.user_data['idx']]
    answer_text = f"*{word['hebrew']}* [{word['transcription']}]\nПеревод: {word['translation']}"
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
            return ConversationHandler.END

        conjugation_candidate = db_read_query("SELECT * FROM verb_conjugations WHERE word_id = ? ORDER BY RANDOM() LIMIT 1", (verb_candidate['word_id'],), fetchone=True)
        if conjugation_candidate:
            verb, conjugation = verb_candidate, conjugation_candidate
            break
        else:
            logger.warning(f"Ошибка целостности данных: у глагола {verb_candidate['hebrew']} (id: {verb_candidate['word_id']}) нет спряжений. Попытка {i+1}/{VERB_TRAINER_RETRY_ATTEMPTS}")

    if not verb or not conjugation:
        await query.edit_message_text("Возникла проблема с данными для тренировки.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=CB_TRAIN_MENU)]]))
        return ConversationHandler.END

    context.user_data['answer'] = dict(conjugation)
    await query.edit_message_text(f"Глагол: *{verb['hebrew']}*\nНапишите форму для: *{conjugation['tense']}, {conjugation['person']}*", parse_mode=ParseMode.MARKDOWN)
    return AWAITING_VERB_ANSWER

async def check_verb_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    correct = context.user_data['answer']
    if update.message.text.strip() == correct['hebrew_form']:
        await update.message.reply_text(f"✅ Верно! *{correct['hebrew_form']}*", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"❌ Неверно. Правильно: *{correct['hebrew_form']}*", parse_mode=ParseMode.MARKDOWN)
    db_write_query("UPDATE user_dictionary SET next_review_at = ? WHERE user_id = ? AND word_id = ?", (datetime.now() + timedelta(days=1), update.effective_user.id, correct['word_id']))
    keyboard = [[InlineKeyboardButton("🔥 Продолжить", callback_data=CB_VERB_TRAINER_START)], [InlineKeyboardButton("⬅️ В меню", callback_data=CB_TRAIN_MENU)]]
    await update.message.reply_text("Что дальше?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

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
    """Обработчик для отображения карточки слова по его ID."""
    query = update.callback_query
    await query.answer()
    word_id = int(query.data.split('_')[-1])
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    
    word_data = db_read_query("SELECT * FROM cached_words WHERE word_id = ?", (word_id,), fetchone=True)
    if word_data:
        await display_word_card(context, user_id, chat_id, dict(word_data), message_id=message_id)
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
        },
        fallbacks=[
            CallbackQueryHandler(end_training, pattern=f"^{CB_END_TRAINING}$"),
            CallbackQueryHandler(back_to_main_menu, pattern="^main_menu$"),
            CallbackQueryHandler(training_menu, pattern=f"^{CB_TRAIN_MENU}$")
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
