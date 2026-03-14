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
        Optimized bulk inserts records with caching and batched processing.
        """
        total_records = len(records)
        stats = {"successful": 0, "failed": 0}

        self.logger.info(
            f"Starting optimized bulk insert of {total_records} records..."
        )

        # Pre-cache organizations to avoid repeated lookups
        org_cache = await self._build_org_cache(records)

        # Group records by clean_name for disambiguation
        self.logger.info(f"Grouping {total_records} records by name...")
        grouped_records = defaultdict(list)
        for record in records:
            grouped_records[record["clean_name"]].append(record)

        self.logger.info(
            f"Grouped into {len(grouped_records)} unique names."
        )

        # Process groups in batches to avoid memory issues
        name_groups = list(grouped_records.items())
        for i in range(
            0, len(name_groups), batch_size // 10
        ):  # Smaller batches for name groups
            batch_groups = name_groups[i : i + batch_size // 10]
            batch_num = (i // (batch_size // 10)) + 1
            total_batches = (len(name_groups) + (batch_size // 10) - 1) // (
                batch_size // 10
            )

            self.logger.info(
                f"Processing name group batch {batch_num}/{total_batches}"
            )

            await self._process_name_groups_batch(
                batch_groups, org_cache, stats
            )

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

    async def _build_org_cache(
        self, records: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Pre-cache organization IDs to avoid repeated lookups."""
        self.logger.info("Building organization cache...")
        org_cache = {}
        unique_orgs = set()

        for record in records:
            if record.get("url"):
                unique_orgs.add(record["url"])

        self.logger.info(
            f"Caching {len(unique_orgs)} unique organizations..."
        )

        # Batch lookup organizations
        for org_url in unique_orgs:
            try:
                org = await self.org_service.orgs_repo.find_by_url(org_url)
                if org:
                    org_cache[org_url] = org["id"]
            except Exception as e:
                self.logger.warning(
                    f"Failed to cache org with URL {org_url}: {e}"
                )

        self.logger.info(f"Cached {len(org_cache)} organizations")
        return org_cache

    async def _process_name_groups_batch(
        self,
        name_groups: List[tuple],
        org_cache: Dict[str, int],
        stats: Dict[str, int],
    ):
        """Process a batch of name groups with optimizations."""
        for name, name_group_records in name_groups:
            try:
                # Use simplified clustering for better performance
                person_clusters = await self._fast_cluster_records(
                    name_group_records, org_cache
                )

                # Process clusters with batched inserts
                for i, cluster in enumerate(person_clusters):
                    await self._process_person_cluster_optimized(
                        cluster=cluster,
                        person_name=name,
                        disambiguation_key=i + 1,
                        org_cache=org_cache,
                        stats=stats,
                    )

            except Exception as e:
                self.logger.error(
                    f"Failed to process group for name '{name}': {e}",
                    exc_info=True,
                )
                stats["failed"] += len(name_group_records)

    async def _fast_cluster_records(
        self, records: List[Dict[str, Any]], org_cache: Dict[str, int]
    ) -> List[List[Dict[str, Any]]]:
        """
        Simplified clustering that avoids expensive database lookups.
        Uses basic temporal and organizational overlap detection.
        """
        if len(records) == 1:
            return [records]

        # Sort by start date for temporal analysis
        sorted_records = sorted(records, key=lambda x: x["start_date"])
        clusters = []

        for record in sorted_records:
            best_cluster_index = -1

            # Find the best cluster based on simple heuristics
            for i, cluster in enumerate(clusters):
                # Check if this record can fit in this cluster
                has_conflict = False
                for cluster_record in cluster:
                    # Simple temporal conflict check
                    if (
                        record["start_date"] <= cluster_record["end_date"]
                        and record["end_date"]
                        >= cluster_record["start_date"]
                    ):
                        # Same organization during overlap = likely same person
                        if record.get("url") == cluster_record.get("url"):
                            has_conflict = False
                            break
                        else:
                            has_conflict = True
                            break

                if not has_conflict:
                    best_cluster_index = i
                    break

            if best_cluster_index >= 0:
                clusters[best_cluster_index].append(record)
            else:
                clusters.append([record])

        return clusters

    async def _process_person_cluster_optimized(
        self,
        cluster: List[Dict[str, Any]],
        person_name: str,
        disambiguation_key: int,
        org_cache: Dict[str, int],
        stats: Dict[str, int],
        max_retries: int = 3,
    ):
        """
        Optimized version that uses cached org lookups and bulk inserts with retry logic.
        """
        if not cluster:
            return

        for attempt in range(max_retries):
            try:
                async with self.people_repo.db.transaction():
                    # Create person record
                    first_record = cluster[0]
                    person_id = await self.people_repo.create(
                        {
                            "name": person_name,
                            "clean_name": first_record["clean_name"],
                            "tel": first_record.get("tel"),
                            "email": first_record.get("email"),
                            "disambiguation_key": disambiguation_key,
                            "metadata": {
                                "raw_name": first_record.get(
                                    "raw_name", ""
                                ),
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

                    # Batch process employment records
                    employment_batch = []
                    for record in cluster:
                        # Use cached org lookup first
                        org_id = org_cache.get(record.get("url"))

                        if not org_id:
                            # Fallback to individual lookup if not cached
                            org_id = await self.org_service._get_org_id(
                                record["org"],
                                record.get("url"),
                                record.get("parent_org_name"),
                                record.get("parent_org_url"),
                            )

                        if org_id:
                            employment_batch.append(
                                {
                                    "person_id": person_id,
                                    "org_id": org_id,
                                    "rank": record["rank"],
                                    "start_date": record["start_date"],
                                    "end_date": record["end_date"],
                                    "tenure_days": record.get(
                                        "tenure_days"
                                    ),
                                    "raw_name": record.get("raw_name", ""),
                                    "metadata": {
                                        "lower_name": record.get(
                                            "lower_name", ""
                                        ),
                                        "source_url_for_employment": record.get(
                                            "url", ""
                                        ),
                                    },
                                }
                            )
                        else:
                            self.logger.warning(
                                f"Failed to find/create org for: {record['org']}"
                            )
                            stats["failed"] += 1

                    # Bulk insert employment records
                    for employment_data in employment_batch:
                        employment_id = await self.employment_repo.create(
                            employment_data
                        )
                        if employment_id:
                            stats["successful"] += 1
                        else:
                            stats["failed"] += 1

                # If successful, break out of retry loop
                return

            except Exception as e:
                if attempt < max_retries - 1:
                    self.logger.warning(
                        f"Attempt {attempt + 1}/{max_retries} failed for person '{person_name}': {e}. Retrying..."
                    )
                else:
                    self.logger.error(
                        f"All {max_retries} attempts failed for person '{person_name}': {e}",
                        exc_info=True,
                    )
                    stats["failed"] += len(cluster)
            # retry for failed records

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
