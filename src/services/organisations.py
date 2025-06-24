from typing import List, Dict, Any, Optional
from src.repositories.organisations import OrganisationsRepository
import logging


class OrganisationService:
    def __init__(
        self,
        orgs_repo: OrganisationsRepository,
    ):
        self.orgs_repo = orgs_repo
        self.logger = logging.getLogger(__name__)

    async def preseed_organizations(
        self, org_hierarchy_data: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Pre-seeds organizations based on a list of hierarchy data using a
        single transaction and an in-memory map for high performance.
        Correctly tracks created vs. updated records.
        """
        self.logger.info(
            f"Starting pre-seeding of {len(org_hierarchy_data)} organizations."
        )

        sorted_org_data = sorted(
            org_hierarchy_data, key=lambda x: len(x.get("parts", []))
        )

        url_to_org_map: Dict[str, Dict[str, Any]] = {}
        created_count = 0
        updated_count = 0
        failed_count = 0

        try:
            async with self.orgs_repo.db.transaction():
                for org_to_seed in sorted_org_data:
                    current_org_name = org_to_seed.get("org")
                    current_org_url = org_to_seed.get("url")
                    parent_org_url_from_seed = org_to_seed.get(
                        "sub_parent_org_url"
                    )

                    if not current_org_name or not current_org_url:
                        self.logger.warning(
                            f"Skipping record due to missing name or URL: {org_to_seed}"
                        )
                        failed_count += 1
                        continue

                    # --- LOGIC TO RESTORE UPDATE COUNT ---
                    # 1. Check if the org already exists in the DB from a previous run.
                    # We must do this before the create call.
                    existing_org = await self.orgs_repo.find_by_url(
                        current_org_url
                    )
                    is_update = existing_org is not None

                    parent_org_id_for_current = None
                    department_for_current_org = None

                    if parent_org_url_from_seed:
                        parent_org_obj = None
                        if parent_org_url_from_seed in url_to_org_map:
                            parent_org_obj = url_to_org_map[
                                parent_org_url_from_seed
                            ]
                        else:
                            parent_org_obj = (
                                await self.orgs_repo.find_by_url(
                                    parent_org_url_from_seed
                                )
                            )

                        if parent_org_obj:
                            parent_org_id_for_current = parent_org_obj["id"]
                            department_for_current_org = parent_org_obj[
                                "name"
                            ]
                        else:
                            self.logger.warning(
                                f"For org '{current_org_name}', parent with URL '{parent_org_url_from_seed}' not found. Creating as top-level."
                            )

                    org_metadata = {
                        "type": "organization",
                        "source": "pre-seeded",
                        "sgdi_entity_type": org_to_seed.get(
                            "sgdi_entity_type"
                        ),
                        "first_observed": org_to_seed.get("first_observed"),
                        "last_observed": org_to_seed.get("last_observed"),
                        "parts": org_to_seed.get("parts"),
                    }
                    cleaned_org_metadata = {
                        k: v
                        for k, v in org_metadata.items()
                        if v is not None
                    }
                    org_creation_data = {
                        "name": current_org_name,
                        "department": department_for_current_org,
                        "url": current_org_url,
                        "parent_org_id": parent_org_id_for_current,
                        "metadata": cleaned_org_metadata,
                    }

                    created_or_updated_id = await self.orgs_repo.create(
                        org_creation_data
                    )

                    if created_or_updated_id:
                        # 2. Increment the correct counter based on our earlier check.
                        if is_update:
                            updated_count += 1
                        else:
                            created_count += 1

                        url_to_org_map[current_org_url] = {
                            "id": created_or_updated_id,
                            "name": current_org_name,
                        }
                    else:
                        self.logger.error(
                            f"Failed to pre-seed or update organization '{current_org_name}'"
                        )
                        failed_count += 1

        except Exception as e:
            self.logger.error(
                f"Exception during pre-seeding transaction, rolling back all changes. Error: {e}",
                exc_info=True,
            )
            return {
                "created": 0,
                "updated": 0,
                "failed": len(org_hierarchy_data),
            }

        self.logger.info(
            f"Pre-seeding complete. Created: {created_count}, Updated: {updated_count}, Failed/Skipped: {failed_count}"
        )
        return {
            "created": created_count,
            "updated": updated_count,
            "failed": failed_count,
        }

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

    async def _get_parent_org_id(
        self, parent_name: Optional[str], parent_url: Optional[str]
    ) -> Optional[int]:
        """Helper to find or create a parent organization."""
        if not parent_name:
            return None

        parent_org_id = None
        parent_org_obj = await self.orgs_repo.find_by_url(parent_url)

        if parent_org_obj:
            parent_org_id = parent_org_obj["id"]
        elif (
            parent_url
        ):  # If not found by name, try to create if URL is available
            self.logger.debug(
                f"Parent org '{parent_name}' not found. Attempting to create with URL: {parent_url}."
            )

            # parse the parent name to get department if needed
            parsed_parent = self._parse_org_details(parent_name)
            # For a parent org created this way, its own parent_org_id is None.
            # Department for such parent orgs might be None or same as name.
            created_id = await self.orgs_repo.create(
                {
                    "name": parsed_parent.get("name"),
                    "department": parsed_parent.get(
                        "department"
                    ),  # Or parent_name if it's a ministry-level entity
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
                self.logger.debug(
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

    async def _get_org_id(
        self,
        org_full_name: str,
        org_url: Optional[str] = None,
        parent_org_name: Optional[str] = None,
        parent_org_url: Optional[str] = None,
    ) -> Optional[int]:
        """Helper to find or create an organization by its full name and URL."""
        org = await self.orgs_repo.find_by_url(org_url)
        if org:
            return org["id"]
        # parent org
        parent_org_id = await self._get_parent_org_id(
            parent_org_name, parent_org_url
        )

        # If not found, create a new organization
        self.logger.warning(
            f"Organization '{org_full_name}' not found by URL '{org_url}'. Creating a new organization."
        )
        parsed_org = self._parse_org_details(org_full_name)
        org_data = {
            "name": parsed_org["name"],
            "department": parsed_org["department"],
            "parent_org_id": parent_org_id,
            "url": org_url,
            "metadata": {
                "type": "organization",
                "source_full_name": org_full_name,
            },
        }
        return await self.orgs_repo.create(org_data)

    async def get_organization_subtree(
        self, parent_org_id: int
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all descendant organizations (the entire subtree) for a
        given parent ID.

        Args:
            parent_org_id: The ID of the top-level organization.

        Returns:
            A list of all descendant organizations.
        """
        self.logger.info(
            f"Fetching all descendants for organization ID {parent_org_id}"
        )
        try:
            # Call the new repository method
            return await self.orgs_repo.get_all_descendants(parent_org_id)
        except Exception as e:
            self.logger.error(
                f"Failed to retrieve organization subtree for ID {parent_org_id}: {e}",
                exc_info=True,
            )
            return []  # Return an empty list on error

    async def get_organization_subtree_at_date(
        self, parent_org_id: int, target_date: str
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all descendant organizations for a given parent ID that
        were active on a specific date. It's like looking at a starship's
        organizational chart at a specific stardate!

        Args:
            parent_org_id: The ID of the top-level organization.
            target_date: The date to check for activity (e.g., '2024-01-15').

        Returns:
            A list of descendant organizations active on the given date.
        """
        self.logger.info(
            f"Fetching descendants for org ID {parent_org_id} active on {target_date}"
        )
        try:
            return await self.orgs_repo.get_all_descendants_at_date(
                parent_org_id, target_date
            )
        except Exception as e:
            self.logger.error(
                f"Failed to retrieve temporal organization subtree for ID {parent_org_id}: {e}",
                exc_info=True,
            )
            return []

    async def get_organization_timeline(
        self, parent_org_id: int
    ) -> List[str]:
        """
        Generates a timeline of significant dates for an organization and
        its entire subtree. These dates correspond to when any sub-org was
        created or dissolved, perfect for powering a UI slider.

        Args:
            parent_org_id: The ID of the top-level organization.

        Returns:
            A sorted list of unique dates as strings (YYYY-MM-DD).
        """
        self.logger.info(
            f"Generating timeline for organization subtree of ID {parent_org_id}"
        )
        try:
            return await self.orgs_repo.get_timeline_dates_for_subtree(
                parent_org_id
            )
        except Exception as e:
            self.logger.error(
                f"Failed to generate organization timeline for ID {parent_org_id}: {e}",
                exc_info=True,
            )
            return []

    async def get_org_descendants_diff_between_dates(
        self,
        parent_org_id: int,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves the difference in descendant organizations between two dates.
        Useful for understanding how an organization's structure has changed
        over time.

        Args:
            parent_org_id: The ID of the top-level organization.
            start_date: The start date for the comparison (YYYY-MM-DD).
            end_date: The end date for the comparison (YYYY-MM-DD).

        Returns:
            A list of descendant organizations that were added or removed
            between the two dates.
        """
        self.logger.info(
            f"Fetching descendants diff for org ID {parent_org_id} between {start_date} and {end_date}"
        )
        return await self.orgs_repo.get_org_descendants_diff_between_dates(
            parent_org_id, start_date, end_date
        )

    async def get_organizations_by_depth(
        self, depth: int
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all organizations at a specific hierarchical depth.
        Depth 1 typically represents top-level ministries, Depth 2 represents
        departments within them, and so on.

        Args:
            depth: The hierarchical depth to query (must be 1 or greater).

        Returns:
            A list of organizations at the specified depth.
        """
        if depth < 1:
            self.logger.warning("Organization depth must be 1 or greater.")
            return []

        self.logger.info(f"Fetching all organizations at depth {depth}")
        try:
            return await self.orgs_repo.find_by_depth(depth)
        except Exception as e:
            self.logger.error(
                f"Failed to retrieve organizations at depth {depth}: {e}",
                exc_info=True,
            )
            return []

    async def get_organization_hierarchy(self) -> List[Dict[str, Any]]:
        """
        Fetches the entire organization hierarchy needed for graph building.
        Selects only the columns required for building the graph structure.
        """
        async with self.orgs_repo.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, parent_org_id
                FROM organizations
                ORDER BY id;
                """
            )
            # No need for _row_to_dict as we are not fetching metadata
            return [dict(row) for row in rows]
