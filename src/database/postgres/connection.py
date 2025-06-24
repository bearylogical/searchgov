import asyncpg
from loguru import logger


class AsyncDatabaseConnection:
    def __init__(
        self,
        host: str = "localhost",
        database: str = "temporal_org",
        user: str = "postgres",
        password: str = "password",
        port: int = 5432,
        min_size: int = 1,
        max_size: int = 10,
    ):
        self.connection_params = {
            "host": host,
            "database": database,
            "user": user,
            "password": password,
            "port": port,
        }
        self.pool_params = {
            "min_size": min_size,
            "max_size": max_size,
        }
        self.pool = None

    async def connect(self):
        try:
            if not self.pool:
                self.pool = await asyncpg.create_pool(
                    **self.connection_params, **self.pool_params
                )
                logger.info("Database connection pool created.")
        except Exception as e:
            logger.error(f"Could not connect to database: {e}")
            raise

    async def close(self):
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed.")

    async def fetch(self, query, *args):
        async with self.pool.acquire() as connection:
            return await connection.fetch(query, *args)

    async def fetchrow(self, query, *args):
        async with self.pool.acquire() as connection:
            return await connection.fetchrow(query, *args)

    async def execute(self, query, *args):
        async with self.pool.acquire() as connection:
            return await connection.execute(query, *args)

    def transaction(self):
        """Provides a context manager for a transaction."""
        if not self.pool:
            raise ConnectionError("Connection pool is not initialized.")
        return self.pool.transaction()

    def acquire(self):
        """Provides a context manager to acquire a connection from the pool."""
        if not self.pool:
            raise ConnectionError("Connection pool is not initialized.")
        return self.pool.acquire()
