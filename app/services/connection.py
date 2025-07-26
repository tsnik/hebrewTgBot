# -*- coding: utf-8 -*-

import logging
import sqlite3
import threading
from types import TracebackType
from typing import Optional, Type

from config import DB_NAME

# Настраиваем логгер
logger = logging.getLogger(__name__)

class DatabaseConnectionManager:
    """
    Manages SQLite database connections, supporting read-only and read-write modes.
    Handles URI-based connections for advanced options like shared in-memory databases.
    """
    def __init__(self, db_name: str, read_only: bool = True):
        self.db_name = db_name
        self.read_only = read_only
        self.connection: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        logger.debug(f"Инициализирован менеджер соединений для '{self.db_name}' (read_only={self.read_only})")

    def __enter__(self) -> sqlite3.Connection:
        with self._lock:
            # Предотвращаем повторное открытие уже существующего соединения
            if self.connection:
                return self.connection

            db_uri = self.db_name
            # Для соединений только для чтения, мы можем использовать URI с `mode=ro`
            if self.read_only:
                # Убеждаемся, что строка начинается с 'file:' для использования URI
                if not db_uri.startswith('file:'):
                    db_uri = f'file:{db_uri}'
                
                # Корректно добавляем параметр mode=ro
                if '?' in db_uri:
                    db_uri = f'{db_uri}&mode=ro'
                else:
                    db_uri = f'{db_uri}?mode=ro'
            
            logger.info(f"Попытка подключения к БД: {db_uri}")
            try:
                self.connection = sqlite3.connect(db_uri, uri=True, check_same_thread=False)
                self.connection.row_factory = sqlite3.Row
                logger.info(f"Успешное подключение к {db_uri}")
            except sqlite3.OperationalError as e:
                # Это может произойти, если БД еще не существует, а мы в режиме read-only
                if "unable to open database file" in str(e) and self.read_only:
                    logger.warning(
                        f"Не удалось открыть БД в режиме read-only (возможно, она не создана). "
                        f"Откат к режиму read-write: {self.db_name}"
                    )
                    # Откатываемся к режиму read-write для создания БД
                    self.connection = sqlite3.connect(self.db_name, uri=True, check_same_thread=False)
                    self.connection.row_factory = sqlite3.Row
                    logger.info(f"Успешное подключение к {self.db_name} в режиме read-write.")
                else:
                    logger.error(f"Не удалось подключиться к БД: {db_uri}", exc_info=True)
                    raise e
            return self.connection

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        if self.connection:
            logger.info(f"Закрытие соединения с БД: {self.db_name}")
            self.connection.close()
            self.connection = None

# Глобальные менеджеры соединений
write_db_manager = DatabaseConnectionManager(DB_NAME, read_only=False)
read_db_manager = DatabaseConnectionManager(DB_NAME, read_only=True)
