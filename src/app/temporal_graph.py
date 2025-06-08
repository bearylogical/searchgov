# temporal_graph.py
from src.database.postgres.connection import DatabaseConnection
from src.database.postgres.schema import SchemaManager
from src.repositories.people import PeopleRepository
from src.repositories.organisations import (
    OrganisationsRepository,
)
from src.repositories.employment import EmploymentRepository
from src.services.employment import EmploymentService
from src.services.query import QueryService
from src.services.analytics import AnalyticsService
from src.services.graph import GraphService
from typing import List, Dict, Any
import logging


class TemporalGraph:
    """Main facade for the temporal graph system"""

    def __init__(
        self,
        host: str = "localhost",
        database: str = "temporal_org",
        user: str = "postgres",
        password: str = "password",
        port: int = 5432,
    ):
        # Setup logging
        logging.basicConfig(level=logging.INFO)

        # Initialize database connection
        self.db_connection = DatabaseConnection(
            host, database, user, password, port
        )

        # Initialize schema manager
        self.schema_manager = SchemaManager(self.db_connection)

        # Initialize repositories
        self.people_repo = PeopleRepository(self.db_connection)
        self.orgs_repo = OrganisationsRepository(self.db_connection)
        self.employment_repo = EmploymentRepository(self.db_connection)

        # Initialize services
        self.employment_service = EmploymentService(
            self.people_repo,
            self.orgs_repo,
            self.employment_repo,
            self.schema_manager,
        )
        self.query_service = QueryService(self.db_connection)
        self.analytics_service = AnalyticsService(self.db_connection)
        self.graph_service = GraphService(self.query_service)

        # register the schema manager to ensure the database is ready
        self.register_pgvector()

    def register_pgvector(self):
        """Register the pgvector extension if not already registered"""
        self.schema_manager.register_pgvector()

    def setup_database(self):
        """Initialize the database schema"""
        self.schema_manager.setup_schema()

    # Employment management
    def add_employment_record(self, record: Dict[str, Any]) -> bool:
        return self.employment_service.add_employment_record(record)

    def bulk_insert_records(
        self, records: List[Dict[str, Any]], batch_size: int = 1000
    ) -> Dict[str, int]:
        return self.employment_service.bulk_insert_records(
            records, batch_size
        )

    # Queries
    def find_colleagues(
        self,
        person_name: str,
        target_date: str = None,
        is_fuzzy: bool = True,
    ) -> List[Dict]:
        """Find colleagues at a specific date or current date if not provided"""
        if target_date is None:
            return self.query_service.find_all_colleagues(
                person_name, is_fuzzy
            )
        return self.query_service.find_colleagues_at_date(
            person_name, target_date, is_fuzzy
        )

    def find_person_by_name(
        self, person_name: str, is_fuzzy: bool = True
    ) -> List[Dict]:
        """Find a person by name, optionally using fuzzy matching"""
        if is_fuzzy:
            return self.people_repo.search_by_name_fuzzy(person_name)
        return self.people_repo.find_by_name(person_name)

    def find_person_by_embedding(
        self, embedding: List[float]
    ) -> List[Dict]:
        """Find a person by their embedding vector"""
        return self.people_repo.search_by_name_embedding(embedding)

    def get_career_progression(
        self,
        person_name: str,
        is_fuzzy: bool = True,
        pg_similarity_threshold: float = 0.3,
        fw_primary_similarity_threshold: float = 0.98,
        max_similar_names: int = 10,
        enable_pairwise: bool = True,
        fw_pairwise_check_threshold: float = 0.8,
        min_links_for_pairwise_check: int = 3,
    ) -> List[Dict]:
        return self.query_service.get_career_progression(
            person_name,
            is_fuzzy,
            min_similarity_threshold=pg_similarity_threshold,
            fw_primary_similarity_threshold=fw_primary_similarity_threshold,
            max_similar_names=max_similar_names,
            enable_pairwise_deep_check=enable_pairwise,
            fw_pairwise_check_threshold=fw_pairwise_check_threshold,
            min_links_for_pairwise_check=min_links_for_pairwise_check,
        )

    def get_network_snapshot(self, target_date: str) -> List[Dict]:
        return self.query_service.get_network_snapshot(target_date)

    # Analytics
    def analyze_organization_turnover(
        self, org_name: str, start_date: str = None, end_date: str = None
    ) -> Dict:
        return self.analytics_service.analyze_organization_turnover(
            org_name, start_date, end_date
        )

    def find_succession_patterns(
        self, max_gap_days: int = 90
    ) -> List[Dict]:
        return self.analytics_service.find_succession_patterns(max_gap_days)

    # Graph analysis
    def find_shortest_path(
        self, person1: str, person2: str, target_date: str = None
    ) -> List[str]:
        return self.graph_service.find_shortest_path(
            person1, person2, target_date
        )

    def calculate_centrality_metrics(
        self, target_date: str = None
    ) -> Dict[str, Dict]:
        return self.graph_service.calculate_centrality_metrics(target_date)

    def close(self):
        """Close database connection"""
        self.db_connection.close()
