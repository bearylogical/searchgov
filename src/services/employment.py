from typing import List, Dict, Any, Optional  # Added Optional
from src.repositories.people import PeopleRepository
from src.repositories.organisations import OrganisationsRepository
from src.repositories.employment import EmploymentRepository
from src.database.postgres.schema import SchemaManager
import logging


class EmploymentService:
    def __init__(
        self,
        people_repo: PeopleRepository,
        orgs_repo: OrganisationsRepository,
        employment_repo: EmploymentRepository,
        schema_manager: SchemaManager,
    ):
        self.people_repo = people_repo
        self.orgs_repo = orgs_repo
        self.employment_repo = employment_repo
        self.schema_manager = schema_manager
        self.logger = logging.getLogger(__name__)

    def _get_or_create_parent_org(
        self, parent_name: Optional[str], parent_url: Optional[str]
    ) -> Optional[int]:
        """Helper to find or create a parent organization."""
        if not parent_name:
            return None

        parent_org_id = None
        parent_org_obj = self.orgs_repo.find_by_name(parent_name)

        if parent_org_obj:
            parent_org_id = parent_org_obj["id"]
        elif (
            parent_url
        ):  # If not found by name, try to create if URL is available
            self.logger.info(
                f"Parent org '{parent_name}' not found. Attempting to create with URL: {parent_url}."
            )
            # For a parent org created this way, its own parent_org_id is None.
            # Department for such parent orgs might be None or same as name.
            created_id = self.orgs_repo.create(
                {
                    "name": parent_name,
                    "department": None,  # Or parent_name if it's a ministry-level entity
                    "url": parent_url,
                    "parent_org_id": None,
                    "metadata": {
                        "type": "organization",
                        "source": "inferred_parent",
                    },
                }
            )
            if created_id:
                parent_org_id = created_id
                self.logger.info(
                    f"Created parent org '{parent_name}' with ID {parent_org_id}."
                )
            else:
                self.logger.warning(
                    f"Failed to create parent org '{parent_name}'. Linking will be skipped for its children."
                )
        else:
            self.logger.warning(
                f"Parent org '{parent_name}' not found and no parent URL provided for creation. Linking will be skipped."
            )
        return parent_org_id

    def _parse_org_details(
        self, org_full_name: str
    ) -> Dict[str, Optional[str]]:
        """Parses full org name into name and department."""
        parts = [p.strip() for p in org_full_name.split(":")]
        if not parts:
            return {
                "name": org_full_name,
                "department": None,
            }  # Should not happen if org_full_name is valid

        specific_name = parts[-1]
        department_name = " : ".join(parts[:-1]) if len(parts) > 1 else None
        return {"name": specific_name, "department": department_name}

    def add_employment_record(self, record: Dict[str, Any]) -> bool:
        """Add a complete employment record, handling organizational hierarchy."""
        try:
            with self.people_repo.db.transaction():
                # 1. Create or get person
                person_id = self.people_repo.create(
                    {
                        "name": record["clean_name"],
                        "clean_name": record["clean_name"],
                        "tel": record.get("tel"),
                        "email": record.get("email"),
                        "embedding": record.get("embedding"),
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

                # 2. Resolve Parent Organization ID
                parent_org_id = self._get_or_create_parent_org(
                    record.get("parent_org_name"),
                    record.get("parent_org_url"),
                )

                # 3. Parse and Create Current (Child) Organization
                current_org_full_name = record["org"]
                parsed_org = self._parse_org_details(current_org_full_name)

                current_org_data = {
                    "name": parsed_org["name"],
                    "department": parsed_org["department"],
                    "url": record.get(
                        "url"
                    ),  # URL of the current/child org
                    "parent_org_id": parent_org_id,
                    "metadata": {
                        "type": "organization",
                        "source_full_name": current_org_full_name,
                        "sgdi_entity_type": record.get(
                            "sgdi_entity_type"
                        ),  # from TSV
                    },
                }
                org_id = self.orgs_repo.create(current_org_data)

                if not org_id:
                    self.logger.error(
                        f"Failed to create organization: {current_org_full_name}"
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
                employment_id = self.employment_repo.create(employment_data)

                return employment_id is not None

        except Exception as e:
            self.logger.error(
                f"Error adding employment record for {record.get('clean_name')} at {record.get('org')}: {e}",
                exc_info=True,
            )
            return False

    def bulk_insert_records(
        self, records: List[Dict[str, Any]], batch_size: int = 1000
    ) -> Dict[str, int]:
        """Bulk insert with proper error handling"""
        total_records = len(records)
        successful = 0
        failed = 0

        # It's highly recommended to process records in an order that ensures
        # parent organizations are created before their children if using this
        # on-the-fly parent creation. Otherwise, consider a multi-pass strategy
        # outside or by modifying this bulk method.
        # For now, this loop processes as is.

        for i in range(0, total_records, batch_size):
            batch = records[i : i + batch_size]
            self.logger.info(
                f"Processing batch {i//batch_size + 1}/{(total_records + batch_size -1)//batch_size}"
            )
            for record_idx, record in enumerate(batch):
                if self.add_employment_record(record):
                    successful += 1
                else:
                    failed += 1
                    self.logger.warning(
                        f"Failed to process record: {record.get('raw_name')} at {record.get('org')}"
                    )
            self.logger.info(
                f"Batch {i//batch_size + 1} processed. Successful: {successful}, Failed: {failed} (cumulative)"
            )

        self.logger.info(
            "Bulk insert process finished. Refreshing materialized views..."
        )
        try:
            self.schema_manager.refresh_materialized_views()
            self.logger.info("Materialized views refreshed successfully.")
        except Exception as e:
            self.logger.error(
                f"Error refreshing materialized views: {e}", exc_info=True
            )

        return {
            "total_processed": total_records,
            "successful": successful,
            "failed": failed,
        }
