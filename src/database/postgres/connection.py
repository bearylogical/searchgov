# database/connection.py
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from loguru import logger
import psycopg2.pool


class DatabaseConnection:
    def __init__(
        self,
        host: str = "localhost",
        database: str = "temporal_org",
        user: str = "postgres",
        password: str = "password",
        port: int = 5432,
    ):
        self.connection_params = {
            "host": host,
            "database": database,
            "user": user,
            "password": password,
            "port": port,
        }
        self.pool = None
        self.logger = logger
        self.connect()

    def connect(self):
        """Establish connection pool to PostgreSQL"""
        try:
            self.pool = psycopg2.pool.SimpleConnectionPool(
                1, 10, **self.connection_params
            )
            self.logger.info("Connected to PostgreSQL successfully")
        except Exception as e:
            self.logger.error(f"Error connecting to PostgreSQL: {e}")
            raise

    @contextmanager
    def get_cursor(self, cursor_factory=None):
        """Context manager for database cursors"""
        conn = None
        try:
            conn = self.pool.getconn()
            cursor = conn.cursor(
                cursor_factory=cursor_factory or RealDictCursor
            )
            try:
                yield cursor
                conn.commit()
            except Exception as e:
                conn.rollback()
                self.logger.error(f"Database operation failed: {e}")
                raise
            finally:
                cursor.close()
        finally:
            if conn:
                self.pool.putconn(conn)

    def execute_with_retry(
        self, query, params=None, cursor_factory=None, retries=1
    ):
        """
        Helper to execute a query with automatic reconnection/retry.
        """
        attempt = 0
        while attempt <= retries:
            try:
                with self.get_cursor(cursor_factory) as cursor:
                    cursor.execute(query, params)
                    if cursor.description:
                        return cursor.fetchall()
                    return None
            except (
                psycopg2.InterfaceError,
                psycopg2.OperationalError,
            ) as e:
                self.logger.warning(
                    f"Connection lost: {e}. Retrying ({attempt+1}/{retries})..."
                )
                attempt += 1
                if attempt > retries:
                    raise
            except Exception:
                raise

    @contextmanager
    def transaction(self):
        """Context manager for transactions (use with get_cursor)"""
        try:
            yield
        except Exception as e:
            self.logger.error(f"Transaction failed: {e}")
            raise

    def close(self):
        """Close all connections in the pool"""
        if self.pool:
            self.pool.closeall()
            self.logger.info("Database connection pool closed")
