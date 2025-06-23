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
from src.services.organisations import OrganisationService
from typing import List, Dict, Any, Optional, Union
from loguru import logger


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
        self.orgs_service = OrganisationService(self.orgs_repo)
        self.employment_service = EmploymentService(
            self.people_repo,
            self.orgs_service,
            self.employment_repo,
            self.schema_manager,
        )
        self.query_service = QueryService(
            self.db_connection, self.employment_repo, self.orgs_repo
        )
        self.analytics_service = AnalyticsService(self.db_connection)
        self.graph_service = GraphService(
            self.query_service, self.orgs_service
        )
        self.logger = logger

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

    def preseed_orgs(
        self, org_hierarchy_data: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Pre-seed organizations based on a hierarchy data list"""
        return self.orgs_service.preseed_organizations(org_hierarchy_data)

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
        self,
        person_name: str,
        is_fuzzy: bool = True,
        include_org_metadata: bool = True,
        include_linked_orgs: bool = True,
    ) -> List[Dict]:
        """Find a person by name, optionally using fuzzy matching"""
        res = []
        if is_fuzzy:
            res = self.people_repo.search_by_name_fuzzy(person_name)
        else:
            res = self.people_repo.find_by_name(person_name)
        if include_org_metadata:
            for person in res:
                person["employment_profile"] = (
                    self.find_employment_profile_by_person_id(person["id"])
                )

        if include_linked_orgs and include_org_metadata:
            for person in res:
                linked_orgs = self.orgs_repo.get_all_ancestors(
                    person["employment_profile"][-1]["org_id"]
                )
                if not linked_orgs:
                    self.logger.warning(
                        f"No linked organizations found for person ID {person['id']} {person}"
                    )
                    linked_orgs = [
                        self.orgs_repo.find_by_org_id(
                            person["employment_profile"][-1]["org_id"]
                        )
                    ]
                    self.logger.info(
                        f"Using single organization for person ID {person['id']}: {linked_orgs}"
                    )
                person["linked_organizations"] = linked_orgs

        return res

    def find_employment_profile_by_person_id(
        self, person_id: int
    ) -> Optional[Dict[str, Any]]:
        """Find a person's profile by their ID"""
        return self.employment_repo.find_by_person_id(person_id)

    def find_person_by_embedding(
        self, embedding: List[float]
    ) -> List[Dict]:
        """Find a person by their embedding vector"""
        return self.people_repo.search_by_name_embedding(embedding)

    def get_career_progression_by_name(
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
        """Get career progression for a person by their name"""
        self.logger.info(
            f"Getting career progression for person: {person_name}, "
        )
        return self.query_service.get_career_progression_by_name(
            person_name,
            is_fuzzy,
            min_similarity_threshold=pg_similarity_threshold,
            fw_primary_similarity_threshold=fw_primary_similarity_threshold,
            max_similar_names=max_similar_names,
            enable_pairwise_deep_check=enable_pairwise,
            fw_pairwise_check_threshold=fw_pairwise_check_threshold,
            min_links_for_pairwise_check=min_links_for_pairwise_check,
        )

    def get_career_progression_by_person_id(
        self, person_id: int
    ) -> List[Dict]:
        """Get career progression for a person by their ID"""
        return self.query_service.get_career_progression_by_person_id(
            person_id
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

    def get_db_stats(self) -> Dict[str, Dict[str, int]]:
        """Get statistics about the database"""
        res = {}
        res["people_count"] = self.people_repo.get_name_stats()
        res["orgs_count"] = self.orgs_repo.get_org_stats()

        res["employment_count"] = (
            self.employment_repo.get_employment_stats()
        )

        return res

    # Graph analysis
    def find_shortest_path(
        self,
        person1: Union[List[int], int],
        person2: Union[List[int], int],
        people_only: bool = False,
        include_metadata: bool = True,
        is_temporal: bool = True,
    ) -> List[str]:
        """Find the shortest path between two people in the graph"""
        logger.info(
            f"Finding shortest path between {person1} and {person2}"
        )

        if is_temporal:
            # If temporal, we need to ensure the path is valid in the temporal context
            res = self.graph_service.find_shortest_temporal_path(
                person1, person2, include_metadata
            )
        else:
            res = self.graph_service.find_shortest_path(
                person1, person2, include_metadata
            )
        if res and include_metadata:
            res_metadata = []
            # Include metadata for each person in the path
            for item in res:
                record = {}
                if "person" in item:
                    record["node_id"] = item
                    record["node_type"] = "person"
                    record["person_id"] = item.split("_")[1]
                    record["name"] = self.people_repo.find_by_person_id(
                        record["person_id"]
                    )["name"]
                    record["employment_profile"] = (
                        self.find_employment_profile_by_person_id(
                            record["person_id"]
                        )
                    )
                elif "org" in item:
                    record["node_id"] = item
                    record["node_type"] = "organization"
                    record["org_id"] = item.split("_")[1]
                    record["name"] = self.orgs_repo.find_by_org_id(
                        record["org_id"]
                    )["name"]
                if record:
                    res_metadata.append(record)
            return res_metadata
        else:
            return self.graph_service.find_shortest_path(
                person1, person2, people_only
            )

    def calculate_centrality_metrics(
        self, target_date: str = None
    ) -> Dict[str, Dict]:
        return self.graph_service.calculate_centrality_metrics(target_date)

    def find_people_by_temporal_overlap(
        self,
        person_id: int,
        name_filter: Optional[str] = None,
        limit: int = 50,
        service_profiles: bool = True,
        fuzzy_matching: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Finds people who are connected to a given person by having worked
        at the same organization during an overlapping time period.

        This is useful for finding potential 'Person B' candidates for a
        connectivity graph after first identifying 'Person A'.

        Args:
            person_id: The unique ID of the person to find connections for.
            limit: The maximum number of connections to return.

        Returns:
            A list of potential connections, each with person 'id' and 'name'.
        """
        if service_profiles:
            res = self.query_service.find_people_by_temporal_overlap(
                person_id, name_filter, limit
            )
            if res and not fuzzy_matching:
                [
                    p.update(
                        dict(
                            employment_profile=self.find_employment_profile_by_person_id(
                                p["id"]
                            )
                        )
                    )
                    for p in res
                ]
                return res
            elif res and fuzzy_matching:
                res_names = [
                    p["name"] for p in res if "name" in p and p["name"]
                ]
                # remove duplicates
                res_names = list(set(res_names))
                res = [
                    self.find_person_by_name(
                        name, is_fuzzy=True, include_org_metadata=True
                    )
                    for name in res_names
                ]
                return res[0]

        return self.query_service.find_people_by_temporal_overlap(
            person_id, name_filter, limit
        )

    def get_base_organizations(self) -> List[Dict[str, Any]]:
        """Get all base organizations in the system"""
        return self.orgs_repo.find_by_depth(1)

    def get_active_descendants(
        self, parent_org_id: int, target_date: str
    ) -> List[Dict[str, Any]]:
        """
        Finds all descendant organizations of a parent that were active
        on a specific date.
        """
        return self.orgs_service.get_organization_subtree_at_date(
            parent_org_id, target_date
        )

    def get_org_timeline_dates(
        self, parent_org_id: int, only_distinct_changes: bool = True
    ) -> List[str]:
        """
        Gets a sorted list of unique dates on which the structure of an
        organization's subtree changed. Ideal for populating a timeline slider.

        Args:
            parent_org_id: The ID of the root organization for the timeline.

        Returns:
            A list of date strings, e.g., ['2021-07-22', '2023-08-13', ...].
        """
        if only_distinct_changes:
            dates = self.orgs_service.get_organization_timeline(
                parent_org_id
            )

            # retrieves subtree dates, which are already distinct
            org_list_per_date = {
                date: self.orgs_service.get_organization_subtree_at_date(
                    parent_org_id, date
                )
                for date in dates
            }
            # Go through each date and remove any dates that have no changes compared to the previous date
            filtered_dates = []
            previous_orgs = None
            for date, orgs in sorted(org_list_per_date.items()):
                if previous_orgs is None or orgs != previous_orgs:
                    filtered_dates.append(date)
                previous_orgs = orgs
            self.logger.debug(
                f"From {len(dates)} dates, filtered to {len(filtered_dates)} distinct dates."
            )
            return filtered_dates
        return self.orgs_service.get_organization_timeline(parent_org_id)

    def get_org_descendants_diff_between_dates(
        self,
        parent_org_id: int,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        """
        Gets the difference in descendant organizations between two dates.
        Useful for visualizing changes in an organization's structure over time.

        Args:
            parent_org_id: The ID of the root organization.
            start_date: The starting date for the comparison.
            end_date: The ending date for the comparison.

        Returns:
            A list of dictionaries representing the differences in descendants.
        """
        return self.orgs_service.get_org_descendants_diff_between_dates(
            parent_org_id, start_date, end_date
        )

    def close(self):
        """Close database connection"""
        self.db_connection.close()
