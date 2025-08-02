import os
import pytest
from yoyo import get_backend, read_migrations
import psycopg2
from psycopg2.extras import DictCursor
import uuid

import config
import dal.unit_of_work
from dal.unit_of_work import UnitOfWork
from dal.repositories import UserSettingsRepository
import services.connection
from services.connection import DatabaseConnectionManager

# Получаем URL тестовой базы данных из переменной окружения
TEST_DATABASE_URL = os.getenv("DATABASE_URL")
if not TEST_DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set for tests")


@pytest.fixture(scope="session")
def db_schema():
    """
    Session-scoped fixture to set up and tear down the database schema.
    This ensures migrations are run only once per test session.
    """
    backend = get_backend(TEST_DATABASE_URL)
    migrations = read_migrations("app/migrations_postgres")

    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))

    yield

    with backend.lock():
        backend.rollback_migrations(backend.to_rollback(migrations))


@pytest.fixture(scope="function")
def db_separate_schema():
    """
    Фикстура для создания, установки и удаления схемы для каждого теста.
    """
    # 1. Генерация уникального имени для схемы
    schema_name = f"test_schema_{uuid.uuid4().hex}"

    # Настройки подключения
    conn = psycopg2.connect(TEST_DATABASE_URL, cursor_factory=DictCursor)
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        # 2. Создание схемы
        cursor.execute(f"CREATE SCHEMA {schema_name};")
        conn.commit()

        # 3. Установка search_path для текущей сессии
        cursor.execute(f"SET search_path TO {schema_name};")
        conn.commit()

        backend = get_backend(f"{TEST_DATABASE_URL}?schema={schema_name}")
        migrations = read_migrations("app/migrations_postgres")

        with backend.lock():
            backend.apply_migrations(backend.to_apply(migrations))
        conn.commit()

        # 4. Возвращаем соединение для использования в тесте
        yield conn, schema_name

    finally:
        # 5. Удаление схемы после завершения теста
        cursor.execute(f"DROP SCHEMA {schema_name} CASCADE;")
        conn.commit()
        cursor.close()
        conn.close()


@pytest.fixture(scope="function")
def db_session(db_schema):
    """
    Function-scoped fixture to provide a transactional session for each test.
    """
    conn = psycopg2.connect(TEST_DATABASE_URL, cursor_factory=DictCursor)
    conn.autocommit = False

    try:
        conn.cursor().execute("BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;")
        yield conn
    finally:
        # Clean up by rolling back any changes made during the test
        conn.rollback()
        conn.close()


@pytest.fixture(scope="function")
def patch_db_url(monkeypatch, db_separate_schema):
    """
    Autouse fixture to patch the DATABASE_URL in the config and recreate
    the global db_manager for each test function, ensuring isolation.
    """
    # 1. Патчим URL в конфиге
    monkeypatch.setattr(config, "DATABASE_URL", TEST_DATABASE_URL)

    _, db_schema = db_separate_schema

    # 2. Создаем НОВЫЙ менеджер соединений для этого теста
    # Это ключевой момент для изоляции тестов. Каждый тест получает свой
    # собственный менеджер, который будет использовать пропатченный URL.
    new_manager = DatabaseConnectionManager(
        db_url=TEST_DATABASE_URL, db_schema=db_schema
    )

    # 3. Патчим глобальный db_manager в модулях, где он используется
    monkeypatch.setattr(services.connection, "db_manager", new_manager)
    monkeypatch.setattr(dal.unit_of_work, "db_manager", new_manager)


@pytest.fixture(scope="function")
def unique_user_id() -> int:
    """
    Фикстура для генерации уникального user_id для каждого теста.
    Мы используем часть UUID, преобразованную в число, чтобы избежать конфликтов.
    """
    # SQLite не поддерживает UUID, поэтому используем int.
    # Для PostgreSQL можно было бы использовать UUID.
    return uuid.uuid4().int % (10**9)


@pytest.fixture(scope="function")
def user_settings_repo(db_session, unique_user_id):
    """Фикстура для создания репозитория и тестового пользователя."""
    connection = db_session
    # Добавляем пользователя, чтобы не нарушать FOREIGN KEY constraint
    connection.cursor().execute(
        "INSERT INTO users (user_id) VALUES (%s);", (unique_user_id,)
    )
    yield UserSettingsRepository(connection)


@pytest.fixture(scope="function")
def unique_user(unique_user_id):
    with UnitOfWork() as uow:
        uow.user_dictionary.add_user(unique_user_id, "TEST", None)
    yield unique_user_id
