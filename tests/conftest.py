import asyncio
import os
import subprocess
import sys

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

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
    yield engine
    await engine.dispose()
    await drop_test_database()


# Deviation: migrations run via subprocess because alembic/env.py spins up its
# own asyncio loop (async_engine_from_config), which conflicts with pytest's
# running loop when using in-process command.upgrade.
@pytest.fixture(scope="session", autouse=True)
async def applied_migrations(test_database):
    env = dict(os.environ)
    env["DATABASE_URL"] = settings.database_url_test
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=env,
    )