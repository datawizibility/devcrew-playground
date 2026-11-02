import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import create_test_database, drop_test_database


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def test_database():
    await drop_test_database()
    await create_test_database()
    engine = create_async_engine(settings.database_url_test)
    # Migrations are applied by Task 4's fixture once models exist.
    yield engine
    await engine.dispose()
    await drop_test_database()