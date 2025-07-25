# tests/conftest.py
import pytest
import asyncio
import sqlite3
import os
from unittest.mock import AsyncMock, Mock, patch

import pytest_asyncio

# Убедитесь, что импорты соответствуют вашей структуре проекта.
# Если код в папке 'app', используйте 'from app import ...'
from services import database
import config

TEST_USER_ID = 123456789
TEST_CHAT_ID = 987654321


@pytest.fixture(scope="session")
def event_loop():
    """Создает экземпляр цикла событий по умолчанию для каждой тестовой сессии."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
def test_db(monkeypatch):
    """
    Создает единственное соединение с БД в памяти и перехватывает все
    попытки создать новое соединение или закрыть существующее, используя
    безопасный класс-обертку.
    """

    # 1. Создаем класс-обертку (прокси) для соединения с БД.
    class MockConnection:
        def __init__(self, real_connection):
            self._real_conn = real_connection

        def close(self):
            """Перехватываем вызов close и ничего не делаем."""
            pass

        def __getattr__(self, name):
            """Передаем все остальные вызовы (cursor, commit и т.д.) настоящему соединению."""
            return getattr(self._real_conn, name)

    # 2. Создаем настоящее соединение и оборачиваем его в наш прокси.
    real_con = sqlite3.connect(":memory:", check_same_thread=False)
    real_con.row_factory = sqlite3.Row
    mock_con = MockConnection(real_con)

    # 3. Перехватываем sqlite3.connect. Теперь любой код, который попытается
    # создать соединение, вместо этого получит наш безопасный прокси-объект.
    monkeypatch.setattr(sqlite3, "connect", lambda *args, **kwargs: mock_con)

    # 4. Заменяем очередь записи, чтобы операции выполнялись немедленно и синхронно.
    def execute_write_synchronously(task):
        if task is None:
            return
        # Эта функция будет использовать наш прокси 'mock_con' через перехваченный sqlite3.connect
        try:
            if callable(task): # Обработка транзакций
                cursor = mock_con.cursor()
                cursor.execute("BEGIN")
                task(cursor)
                mock_con.commit()
            else: # Обработка обычных запросов
                query, params, is_many = task
                cursor = mock_con.cursor()
                if is_many:
                    cursor.executemany(query, params)
                else:
                    cursor.execute(query, params)
                mock_con.commit()
        except sqlite3.Error as e:
            print(f"DB-WRITE-MOCK-ERROR: {e}")
            mock_con.rollback()
            raise

    mock_queue = Mock()
    mock_queue.put.side_effect = execute_write_synchronously
    monkeypatch.setattr(database, "DB_WRITE_QUEUE", mock_queue)

    # 5. Патчим создание директорий, чтобы избежать ошибок с файловой системой.
    monkeypatch.setattr(os, "makedirs", lambda *args, **kwargs: None)

    # 6. Инициализируем схему БД.
    database.init_db()

    yield real_con  # Предоставляем тесту настоящее соединение для проверок

    # 7. После того, как тест полностью завершился, закрываем настоящее соединение.
    real_con.close()


@pytest.fixture
def mock_context():
    """Создает мок объекта context для Telegram."""
    context = AsyncMock()
    context.bot.send_message.return_value = AsyncMock(message_id=111)
    context.bot.edit_message_text.return_value = AsyncMock(message_id=111)
    return context
