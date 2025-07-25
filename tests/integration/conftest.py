import pytest
import asyncio
from telegram.ext import Application
from unittest.mock import AsyncMock, Mock, patch
import pytest_asyncio
import sqlite3

from app.services import database

from app.services.database import init_db, db_worker, DB_WRITE_QUEUE

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()



class SynchronousQueue:
    def __init__(self, connection):
        self.connection = connection

    def put(self, task):
        # Если пришел сигнал остановки, ничего не делаем
        if task is None:
            return

        query, params, *_ = task

        cursor = self.connection.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        self.connection.commit()

    def get(self): # Для совместимости, если кто-то вызовет
        return None

    def task_done(self): # Для совместимости
        pass

    def join(self): # Для совместимости
        pass


@pytest_asyncio.fixture(scope="function")
def test_db(monkeypatch):
    """
    Создает in-memory БД и подменяет очередь на синхронный мок.
    Все вызовы db_write_query будут выполняться немедленно.
    """
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row

    # 2. Подменяем реальную очередь на наш синхронный мок
    sync_queue = SynchronousQueue(con)
    monkeypatch.setattr(database, "DB_WRITE_QUEUE", sync_queue)

    # Мокируем только чтение, т.к. запись теперь идет через наш мок
    def mock_db_read_query(query, params=None):
        cursor = con.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor.fetchall()

    monkeypatch.setattr(database, "db_read_query", mock_db_read_query)

    # 3. Инициализируем схему БД (запрос на создание таблиц сразу выполнится)
    database.init_db()

    yield con

    con.close()

TEST_USER_ID = 123456789

@pytest.fixture
def app(test_db):
    """Create a mock application for testing."""
    application = Mock(spec=Application)
    application.bot = AsyncMock()
    return application

@pytest_asyncio.fixture(scope="function")
async def init_db_for_test(test_db):
    """
    Initializes the database for a test function.
    This is a combination of test_db and an async init.
    """
    # test_db fixture already patches DB_NAME and calls init_db()
    # No need to do anything else here, just depend on test_db
    yield