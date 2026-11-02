from sqlalchemy import text


async def test_engine_connects_to_test_database(test_database):
    engine = test_database
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


async def test_get_db_yields_session_in_transaction():
    from app.db import get_db

    agen = get_db()
    session = await agen.__anext__()
    try:
        assert session.in_transaction()
    finally:
        await agen.aclose()