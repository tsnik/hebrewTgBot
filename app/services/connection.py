# -*- coding: utf-8 -*-
import logging
import sqlite3
import threading
from types import TracebackType
from typing import Optional, Type, Union

import psycopg2
from psycopg2.extensions import connection as psycopg2_connection
from psycopg2.extras import DictCursor

from config import DATABASE_URL

logger = logging.getLogger(__name__)

# Определяем общий тип для соединений, чтобы использовать в аннотациях
Connection = Union[sqlite3.Connection, psycopg2_connection]


class DatabaseConnectionManager:
    """
    Manages database connections for both SQLite and PostgreSQL.
    The database type is determined by the connection string.
    """

    def __init__(self, db_url: str, db_schema: Optional[str] = None):
        self.db_url = db_url
        self.connection: Optional[Connection] = None
        self._lock = threading.Lock()
        self.is_postgres = self.db_url.startswith("postgres")
        self.db_schema = db_schema
        logger.debug(f"Инициализирован менеджер соединений для '{self.db_url}'")

    def __enter__(self) -> Connection:
        with self._lock:
            if self.connection:
                return self.connection

            logger.info(f"Попытка подключения к БД: {self.db_url}")
            try:
                if self.is_postgres:
                    self.connection = psycopg2.connect(self.db_url)
                    self.connection.cursor_factory = DictCursor  # noqa
                    if self.db_schema:
                        self.connection.cursor().execute(
                            f"SET search_path TO {self.db_schema};"
                        )
                        self.connection.commit()
                else:
                    # Для SQLite используем старую логику с URI
                    self.connection = sqlite3.connect(
                        self.db_url, uri=True, check_same_thread=False
                    )
                    self.connection.row_factory = sqlite3.Row

                logger.info(f"Успешное подключение к {self.db_url}")
                return self.connection
            except (sqlite3.OperationalError, psycopg2.OperationalError) as e:
                logger.error(
                    f"Не удалось подключиться к БД: {self.db_url}", exc_info=True
                )
                raise e

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        if self.connection:
            logger.info(f"Закрытие соединения с БД: {self.db_url}")
            self.connection.close()
            self.connection = None


# Глобальный менеджер соединений, использующий DATABASE_URL из конфига
db_manager = DatabaseConnectionManager(DATABASE_URL)
