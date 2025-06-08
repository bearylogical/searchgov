# repositories/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from src.database.postgres.connection import DatabaseConnection


class BaseRepository(ABC):
    def __init__(self, db_connection: DatabaseConnection):
        self.db = db_connection

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> Optional[int]:
        pass

    @abstractmethod
    def find_by_id(self, id: int) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        pass
