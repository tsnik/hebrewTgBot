import pytest
import sqlite3
from unittest.mock import patch
from app.dal.unit_of_work import UnitOfWork

from yoyo import get_backend, read_migrations

@pytest.fixture(scope="session")
def memory_db():
    """
    Fixture to set up a shared in-memory SQLite database for the test session.
    """
    # Using "file:memdb1?mode=memory&cache=shared" allows the in-memory database
    # to be shared between different connections, which is crucial for testing
    # since our app code will open new connections.
    db_uri = "file:memdb1?mode=memory&cache=shared"

    # yoyo-migrations needs the sqlite:/// prefix
    backend = get_backend(f"sqlite:///{db_uri}")
    migrations = read_migrations("app/migrations")

    # Keep one connection open for the duration of the tests to ensure the
    # in-memory database persists.
    with backend.lock(), backend.connection:
        backend.apply_migrations(backend.to_apply(migrations))
        yield db_uri

import dal.unit_of_work
import services.connection

@pytest.fixture(autouse=True)
def patch_db_name(monkeypatch, memory_db):
    """
    Autouse fixture to patch the DB_NAME in the config for all tests.
    """
    monkeypatch.setattr(dal.unit_of_work, "DB_NAME", memory_db)
    monkeypatch.setattr(services.connection, "DB_NAME", memory_db)
