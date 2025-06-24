from collections import defaultdict
from typing import List, Dict, Any

# Your other imports
from src.repositories.people import PeopleRepository
from src.repositories.employment import EmploymentRepository
from src.services.organisations import OrganisationService
from src.database.postgres.schema import SchemaManager

# Import the new service you created
from src.services.disambiguation import DisambiguationService
from loguru import logger


class EmploymentService:
    def __init__(
        self,
        people_repo: PeopleRepository,
        org_service: OrganisationService,
        employment_repo: EmploymentRepository,
        schema_manager: SchemaManager,
    ):
        self.people_repo = people_repo
        self.org_service = org_service
        self.employment_repo = employment_repo
        self.schema_manager = schema_manager
        self.logger = logger

        # Instantiate the disambiguation service, passing it the orgs repo
        # which is available via the org_service.
        self.disambiguation_service = DisambiguationService(
            orgs_repo=self.org_service.orgs_repo
        )

    async def bulk_insert_records(
        self, records: List[Dict[str, Any]], batch_size: int = 1000
    ) -> Dict[str, int]:
        """
        Bulk inserts records after grouping and disambiguating them to
        correctly identify unique individuals.
        """
        total_records = len(records)
        stats = {"successful": 0, "failed": 0}

        # --- Step 1: Group all records by clean_name ---
        # This is the most critical change. We need all records for a given
        # name together before we can disambiguate.
        self.logger.info(f"Grouping {total_records} records by name...")
        grouped_records = defaultdict(list)
        for record in records:
            grouped_records[record["clean_name"]].append(record)
        self.logger.info(
            f"Grouped into {len(grouped_records)} unique names."
        )

        # --- Step 2: Process each name group ---
        for name, name_group_records in grouped_records.items():
            try:
                # --- Step 3: Disambiguate the group into clusters ---
                # Each cluster represents a unique person.
                person_clusters = (
                    self.disambiguation_service.cluster_employment_records(
                        name_group_records
                    )
                )

                # --- Step 4: Process each identified person cluster ---
                for i, cluster in enumerate(person_clusters):
                    # MODIFIED: We no longer create a disambiguated name string.
                    # We will pass the original name and a key instead.
                    await self._process_person_cluster(
                        cluster=cluster,
                        person_name=name,  # Pass the original, clean name
                        disambiguation_key=i + 1,  # Key is 1, 2, 3...
                        stats=stats,
                    )

            except Exception as e:
                self.logger.error(
                    f"Failed to process group for name '{name}': {e}",
                    exc_info=True,
                )
                stats["failed"] += len(name_group_records)

        self.logger.info(
            "Bulk insert process finished. Refreshing materialized views..."
        )
        try:
            await self.schema_manager.refresh_materialized_views()
            self.logger.info("Materialized views refreshed successfully.")
        except Exception as e:
            self.logger.error(
                f"Error refreshing materialized views: {e}", exc_info=True
            )

        return {
            "total_processed": total_records,
            "successful": stats["successful"],
            "failed": stats["failed"],
        }

    async def _process_person_cluster(
        self,
        cluster: List[Dict[str, Any]],
        person_name: str,
        disambiguation_key: int,
        stats: Dict[str, int],
    ):
        """
        Processes a single cluster of records belonging to one unique person.
        Creates one person DB entry and links all their employment records.
        """
        if not cluster:
            return

        try:
            async with self.people_repo.db.transaction():
                # 1. Create ONE person record for this entire cluster.
                # We use the first record in the cluster for metadata.
                first_record = cluster[0]
                person_id = await self.people_repo.create(
                    {
                        "name": person_name,  # Use the unique, disambiguated name
                        "clean_name": first_record["clean_name"],
                        "tel": first_record.get("tel"),
                        "email": first_record.get("email"),
                        "disambiguation_key": disambiguation_key,
                        "metadata": {
                            "raw_name": first_record.get("raw_name", ""),
                            "type": first_record.get("type", "person"),
                        },
                    }
                )

                if not person_id:
                    self.logger.error(
                        f"Failed to create person: {person_name}"
                    )
                    stats["failed"] += len(cluster)
                    return

                # 2. Loop through all employment records in the cluster
                for record in cluster:
                    # 3. Resolve or Create current organization
                    org_id = await self.org_service._get_org_id(
                        record["org"],
                        record.get("url"),
                        record.get("parent_org_name"),
                        record.get("parent_org_url"),
                    )
                    if not org_id:
                        self.logger.warning(
                            f"Failed to find/create org for record: {record['org']}. Skipping employment."
                        )
                        stats["failed"] += 1
                        continue

                    # 4. Create the employment relationship, linking to the new person_id
                    employment_data = {
                        "person_id": person_id,
                        "org_id": org_id,
                        "rank": record["rank"],
                        "start_date": record["start_date"],
                        "end_date": record["end_date"],
                        "tenure_days": record.get("tenure_days"),
                        "raw_name": record.get("raw_name", ""),
                        "metadata": {
                            "lower_name": record.get("lower_name", ""),
                            "source_url_for_employment": record.get(
                                "url", ""
                            ),
                        },
                    }
                    employment_id = await self.employment_repo.create(
                        employment_data
                    )
                    if employment_id:
                        stats["successful"] += 1
                    else:
                        stats["failed"] += 1

        except Exception as e:
            self.logger.error(
                f"Error processing cluster for person '{person_name}': {e}",
                exc_info=True,
            )
            stats["failed"] += len(cluster)

    async def add_employment_record(self, record: Dict[str, Any]) -> bool:
        """Add a complete employment record, handling organizational hierarchy."""
        try:
            async with self.people_repo.db.transaction():
                # 1. Create or get person
                person_id = await self.people_repo.create(
                    {
                        "name": record["clean_name"],
                        "clean_name": record["clean_name"],
                        "tel": record.get("tel"),
                        "email": record.get("email"),
                        "metadata": {
                            "raw_name": record.get("raw_name", ""),
                            "type": record.get("type", "person"),
                        },
                    }
                )
                if not person_id:
                    self.logger.error(
                        f"Failed to create person: {record['clean_name']}"
                    )
                    return False

                # # 2. Resolve Parent Organization ID
                # parent_org_id = self._get_parent_org_id(
                #     record.get("parent_org_name"),
                #     record.get("parent_org_url"),
                # )

                # 3. Resolve or Create current organization
                org_id = await self.org_service._get_org_id(
                    record["org"],
                    record.get("url"),
                    record.get("parent_org_name"),
                    record.get("parent_org_url"),
                )
                if not org_id:
                    self.logger.error(
                        f"Failed to create or find organization: {record['org']}"
                    )
                    return False

                # 4. Create employment relationship
                employment_data = {
                    "person_id": person_id,
                    "org_id": org_id,
                    "rank": record["rank"],
                    "start_date": record["start_date"],
                    "end_date": record["end_date"],
                    "tenure_days": record.get(
                        "tenure_days"
                    ),  # Ensure this key exists or handle None
                    "raw_name": record.get("raw_name", ""),
                    "metadata": {
                        "lower_name": record.get("lower_name", ""),
                        "source_url_for_employment": record.get(
                            "url", ""
                        ),  # Clarify if this is employment specific
                    },
                }
                employment_id = await self.employment_repo.create(
                    employment_data
                )

                return employment_id is not None

        except Exception as e:
            self.logger.error(
                f"Error adding employment record for {record.get('clean_name')} at {record.get('org')}: {e}",
                exc_info=True,
            )
            return False
