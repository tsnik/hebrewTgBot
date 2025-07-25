# -*- coding: utf-8 -*-

import sqlite3
import os
import queue
import threading
import time
from typing import Callable, Optional, Dict, Any, List
from collections.abc import Callable as CallableABC

from ..config import DB_NAME, logger, DB_READ_ATTEMPTS, DB_READ_DELAY

# --- ПОТОКОБЕЗОПАСНОСТЬ И ОЧЕРЕДЬ ЗАПИСИ В БД ---
DB_WRITE_QUEUE = queue.Queue()

def db_worker():
    """
    Worker, который последовательно выполняет запросы на запись в БД
    из очереди для избежания блокировок.
    """
    # Убедимся, что директория для БД существует
    os.makedirs(os.path.dirname(DB_NAME), exist_ok=True)
    
    conn = None
    
    while True:
        try:
            item = DB_WRITE_QUEUE.get()
            if item is None:  # Сигнал для завершения работы
                break
                
            if conn is None:
                conn = sqlite3.connect(DB_NAME, timeout=10)
                # Включаем режим WAL для лучшей производительности
                conn.execute("PRAGMA journal_mode=WAL;")
            
            cursor = conn.cursor()
            
            # Если в очередь передана функция для выполнения в транзакции
            if isinstance(item, CallableABC):
                try:
                    cursor.execute("BEGIN TRANSACTION")
                    item(cursor)
                    conn.commit()
                except Exception as e:
                    logger.error(f"DB-WORKER: Ошибка в транзакции, откатываем. Ошибка: {e}", exc_info=True)
                    conn.rollback()
            # Иначе это стандартный запрос
            else:
                query, params, is_many = item
                if is_many:
                    cursor.executemany(query, params)
                else:
                    cursor.execute(query, params)
                conn.commit()
        except Exception as e:
            logger.error(f"DB-WORKER: Критическая ошибка: {e}", exc_info=True)
            
    if conn:
        conn.close()

def db_write_query(query: str, params: tuple = (), many: bool = False):
    """Помещает запрос на запись (INSERT, UPDATE, DELETE) в очередь."""
    DB_WRITE_QUEUE.put((query, params, many))

def db_transaction(func: Callable[[sqlite3.Cursor], None]):
    """Помещает функцию для выполнения внутри одной транзакции в очередь."""
    DB_WRITE_QUEUE.put(func)

def db_read_query(query: str, params: tuple = (), fetchone: bool = False, fetchall: bool = False):
    """Выполняет запрос на чтение (SELECT) и возвращает результат."""
    try:
        # Используем check_same_thread=False, т.к. чтение может происходить из разных потоков
        conn = sqlite3.connect(DB_NAME, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # Возвращает результаты в виде словарей
        cursor = conn.cursor()
        cursor.execute(query, params)
        result = None
        if fetchone:
            result = cursor.fetchone()
        if fetchall:
            result = cursor.fetchall()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"DB-READ: Ошибка при чтении из БД: {e}")
        return None

def init_db():
    """Инициализирует таблицы и индексы в БД."""
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
    # Индексы для ускорения поиска
    db_write_query("CREATE INDEX IF NOT EXISTS idx_normalized_hebrew ON cached_words(normalized_hebrew)")
    db_write_query("CREATE INDEX IF NOT EXISTS idx_normalized_hebrew_form ON verb_conjugations(normalized_hebrew_form)")
    db_write_query("CREATE INDEX IF NOT EXISTS idx_translations_word_id ON translations(word_id)")

# local_search is removed