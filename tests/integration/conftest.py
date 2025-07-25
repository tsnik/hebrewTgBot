import pytest_asyncio
import asyncio
from telegram.ext import Application
from unittest.mock import AsyncMock, Mock, patch

from app.services.database import init_db, db_worker, DB_WRITE_QUEUE

@pytest_asyncio.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="session")
async def test_db():
    """Fixture to set up and tear down a test database."""
    with patch('app.services.database.DB_NAME', ':memory:'):
        init_db()
        # No need to start a db_worker thread for in-memory db
        yield
        # The in-memory database is automatically discarded

TEST_USER_ID = 123456789
@pytest_asyncio.fixture
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
