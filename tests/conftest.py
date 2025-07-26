import pytest
import sqlite3
from unittest.mock import patch
from app.dal.unit_of_work import UnitOfWork

from yoyo import get_backend, read_migrations

@pytest.fixture
def memory_db_uow():
    backend = get_backend("sqlite:///:memory:")
    migrations = read_migrations("app/migrations")
    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))

    conn = backend.connection
    conn.row_factory = sqlite3.Row

    with patch('dal.unit_of_work.sqlite3.connect') as mock_connect:
        mock_connect.return_value = conn
        yield UnitOfWork(db_name=":memory:")

    conn.close()
