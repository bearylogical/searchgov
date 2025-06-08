# database/connection.py
import psycopg2
from psycopg2.extras import RealDictCursor
import logging
from typing import Dict, Any, Optional
from contextlib import contextmanager


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

        self.conn = None
        self.logger = logging.getLogger(__name__)
        self.connect()

    def connect(self):
        """Establish connection to PostgreSQL"""
        try:
            self.conn = psycopg2.connect(**self.connection_params)
            self.conn.autocommit = False
            self.logger.info("Connected to PostgreSQL successfully")
        except Exception as e:
            self.logger.error(f"Error connecting to PostgreSQL: {e}")
            raise

    @contextmanager
    def get_cursor(self, cursor_factory=None):
        """Context manager for database cursors"""
        cursor = self.conn.cursor(
            cursor_factory=cursor_factory or RealDictCursor
        )
        try:
            yield cursor
        except Exception as e:
            self.conn.rollback()
            self.logger.error(f"Database operation failed: {e}")
            raise
        finally:
            cursor.close()

    @contextmanager
    def transaction(self):
        """Context manager for transactions"""
        try:
            yield
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            self.logger.error(f"Transaction failed: {e}")
            raise

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.logger.info("Database connection closed")
