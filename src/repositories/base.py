# repositories/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from src.database.postgres.connection import DatabaseConnection
from loguru import logger


class BaseRepository(ABC):
    def __init__(self, db_connection: DatabaseConnection):
        self.db = db_connection
        self.logger = logger

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> Optional[int]:
        pass

    @abstractmethod
    def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        pass
