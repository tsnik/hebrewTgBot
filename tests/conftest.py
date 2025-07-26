import pytest
import sqlite3
import uuid
from yoyo import get_backend, read_migrations
from yoyo.backends import SQLiteBackend
import dal.unit_of_work
import services.connection
import config
from services.connection import DatabaseConnectionManager

@pytest.fixture(scope='function')
def monkeypatch_session(request):
    """A session-scoped monkeypatch to use in session-scoped fixtures."""
    from _pytest.monkeypatch import MonkeyPatch
    mpatch = MonkeyPatch()
    yield mpatch
    mpatch.undo()

@pytest.fixture(scope="function")
def memory_db(monkeypatch_session):
    """
    Fixture to set up a shared in-memory SQLite database for the test session.
    
    This fixture patches yoyo-migrations's SQLite connection method to correctly
    handle shared in-memory databases via URI, making it the most robust solution.
    """
    # Этот URI будет использоваться и в нашем патче, и в приложении
    db_uri_for_app = f"file:mem_{uuid.uuid4()}?mode=memory&cache=shared"
    
    # Этот URI мы передаем в yoyo, чтобы он выбрал правильный бэкенд
    db_uri_for_yoyo = f"sqlite:///{db_uri_for_app}"

    master_connection = sqlite3.connect(db_uri_for_app, uri=True, check_same_thread=False)

    # 1. Определяем нашу собственную функцию для подключения
    def patched_sqlite_connect(self, dburi_obj):
        """
        A patched version of yoyo.backends.SQLiteBackend.connect.
        This ignores the parsed dburi_obj and connects directly using our
        full URI string, which is necessary for shared in-memory databases.
        """
        print(f"--- Patched yoyo connect called. Connecting to {db_uri_for_app} ---")
        conn = sqlite3.connect(
            db_uri_for_app,
            uri=True,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.isolation_level = None  # yoyo expects this
        return conn

    # 2. Патчим метод 'connect' в классе SQLiteBackend с помощью сессионного monkeypatch
    monkeypatch_session.setattr(SQLiteBackend, "connect", patched_sqlite_connect)

    # 3. Теперь yoyo будет использовать наш метод для подключения
    backend = get_backend(db_uri_for_yoyo)
    migrations = read_migrations("app/migrations")

    # `backend.connection` теперь будет вызывать наш `patched_sqlite_connect`
    with backend.lock(), backend.connection:
        print("--- Applying migrations using patched yoyo backend ---")
        backend.apply_migrations(backend.to_apply(migrations))
        print("--- Migrations applied successfully ---")

        # 4. Передаем URI в тесты, НАХОДЯСЬ ВНУТРИ блока with.
        # Это гарантирует, что соединение, поддерживающее жизнь БД,
        # останется открытым на всю тестовую сессию.
        yield db_uri_for_app
        
    master_connection.close()
    
    # Блок with завершится здесь, и соединение закроется ПОСЛЕ
    # того, как все тесты в сессии будут выполнены.

import dal.unit_of_work
import services.connection
import config

@pytest.fixture(autouse=True)
def patch_db_name(monkeypatch, memory_db):
    """
    Autouse fixture to patch the DB_NAME in the config for all tests.
    """
    monkeypatch.setattr(dal.unit_of_work, "DB_NAME", memory_db)
    monkeypatch.setattr(services.connection, "DB_NAME", memory_db)
    monkeypatch.setattr(config, "DB_NAME", memory_db)

    # Шаг 2: КЛЮЧЕВОЕ ИЗМЕНЕНИЕ. Заменяем старые синглтоны новыми.
    # Теперь любой код, импортирующий write_db_manager, получит наш
    # новый, чистый экземпляр, подключенный к изолированной БД этого теста.
    monkeypatch.setattr(
        'dal.unit_of_work.write_db_manager',
        DatabaseConnectionManager(db_name=memory_db, read_only=False)
    )