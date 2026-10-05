from typing import AsyncIterator
import asyncpg
from app.config import settings

db_pool: asyncpg.Pool | None = None

async def init_db_pool() -> None:
    global db_pool
    db_pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=settings.DB_POOL_MIN_SIZE,
        max_size=settings.DB_POOL_MAX_SIZE,
    )

async def close_db_pool() -> None:
    global db_pool
    if db_pool:
        await db_pool.close()

async def get_connection() -> AsyncIterator[asyncpg.Connection]:
    if db_pool is None:
        raise RuntimeError("Pool de banco de dados nao inicializado.")
    async with db_pool.acquire() as connection:
        yield connection