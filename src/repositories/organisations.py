from .base import BaseRepository
from typing import Dict, Any, Optional, List
import json


class OrganisationsRepository(BaseRepository):
    def _row_to_dict(self, row: Any) -> Optional[Dict[str, Any]]:
        """
        Private helper to convert a database row to a dict, safely
        parsing the JSON metadata field.
        """
        if not row:
            return None

        data = dict(row)
        metadata = data.get("metadata")

        if isinstance(metadata, str):
            try:
                data["metadata"] = json.loads(metadata)
            except json.JSONDecodeError:
                # Use the logger from BaseRepository if available
                self.logger.warning(
                    f"Could not decode metadata for org_id {data.get('id')}"
                )
                data["metadata"] = {}  # Default to empty dict on error
        return data

    def create(self, data: Dict[str, Any]) -> Optional[int]:
        """
        Create or update an organization record based on its unique URL.
        """
        with self.db.get_cursor() as cur:
            # The ON CONFLICT clause is smart. It keeps existing values if
            # new ones aren't provided, and merges metadata.
            cur.execute(
                """
                INSERT INTO organizations (name, department, url, parent_org_id, metadata)
                VALUES (%(name)s, %(department)s, %(url)s, %(parent_org_id)s, %(metadata)s)
                ON CONFLICT (url) DO UPDATE SET
                    name = EXCLUDED.name, -- Always update name
                    department = COALESCE(EXCLUDED.department, organizations.department),
                    parent_org_id = COALESCE(EXCLUDED.parent_org_id, organizations.parent_org_id),
                    metadata = organizations.metadata || EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id;
            """,
                {
                    "name": data["name"],
                    "department": data.get("department"),
                    "url": data.get("url"),
                    "parent_org_id": data.get("parent_org_id"),
                    "metadata": json.dumps(data.get("metadata", {})),
                },
            )
            result = cur.fetchone()
            return result["id"] if result else None

    def find_by_org_id(self, org_id: int) -> Optional[Dict[str, Any]]:
        """Find an organization by its ID."""
        with self.db.get_cursor() as cur:
            cur.execute(
                "SELECT * FROM organizations WHERE id = %s", (org_id,)
            )
            return self._row_to_dict(cur.fetchone())

    def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find an organization by its name."""
        with self.db.get_cursor() as cur:
            cur.execute(
                "SELECT * FROM organizations WHERE name = %s", (name,)
            )
            # Note: Names may not be unique. Consider returning a list.
            return self._row_to_dict(cur.fetchone())

    def find_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Find an organization by its URL."""
        with self.db.get_cursor() as cur:
            cur.execute(
                "SELECT * FROM organizations WHERE url = %s", (url,)
            )
            return self._row_to_dict(cur.fetchone())

    def get_children(self, parent_org_id: int) -> List[Dict[str, Any]]:
        """Get all direct children of a given parent organization."""
        with self.db.get_cursor() as cur:
            cur.execute(
                "SELECT * FROM organizations WHERE parent_org_id = %s ORDER BY name",
                (parent_org_id,),
            )
            return [self._row_to_dict(row) for row in cur.fetchall()]

    def get_all_descendants_at_date(
        self, parent_org_id: int, target_date: str
    ) -> List[Dict[str, Any]]:
        """
        Recursively get all descendant organizations for a given parent ID
        that were active on a specific date.
        """
        with self.db.get_cursor() as cur:
            # This query first builds the entire descendant tree, then filters
            # it based on the temporal data in the metadata JSONB field.
            cur.execute(
                """
                WITH RECURSIVE org_hierarchy AS (
                    -- Anchor member: the starting parent organization
                    SELECT * FROM organizations WHERE id = %(parent_id)s
                    UNION ALL
                    -- Recursive member: join to find children
                    SELECT o.* FROM organizations o
                    JOIN org_hierarchy h ON o.parent_org_id = h.id
                )
                SELECT * FROM org_hierarchy
                WHERE
                    -- Exclude the parent itself from the final result
                    id != %(parent_id)s
                    -- And apply the temporal filter
                    AND %(target_date)s::date >= COALESCE((metadata->>'first_observed')::date, '1900-01-01'::date)
                    AND %(target_date)s::date <= COALESCE((metadata->>'last_observed')::date, '9999-12-31'::date);
                """,
                {"parent_id": parent_org_id, "target_date": target_date},
            )
            return [self._row_to_dict(row) for row in cur.fetchall()]

    def get_all_descendants(
        self, parent_org_id: int
    ) -> List[Dict[str, Any]]:
        """
        Recursively get all descendant organizations for a given parent ID.
        """
        with self.db.get_cursor() as cur:
            cur.execute(
                """
                WITH RECURSIVE org_hierarchy AS (
                    SELECT * FROM organizations WHERE id = %(parent_id)s
                    UNION ALL
                    SELECT o.* FROM organizations o
                    JOIN org_hierarchy h ON o.parent_org_id = h.id
                )
                SELECT * FROM org_hierarchy WHERE id != %(parent_id)s;
                """,
                {"parent_id": parent_org_id},
            )
            return [self._row_to_dict(row) for row in cur.fetchall()]

    def get_all_ancestors(
        self, org_id: int, sort: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Recursively get all ancestor organizations for a given organization ID.
        """
        with self.db.get_cursor() as cur:
            cur.execute(
                """
                WITH RECURSIVE org_hierarchy AS (
                    SELECT * FROM organizations WHERE id = %(org_id)s
                    UNION ALL
                    SELECT o.* FROM organizations o
                    JOIN org_hierarchy h ON o.id = h.parent_org_id
                )
                SELECT * FROM org_hierarchy WHERE id != %(org_id)s;
                """,
                {"org_id": org_id},
            )
            res = [self._row_to_dict(row) for row in cur.fetchall()]
            if sort:
                res = sorted(
                    res,
                    key=lambda x: len(x.get("metadata", {}).get("parts")),
                )
            return res

    def find_by_depth(self, depth: int) -> List[Dict[str, Any]]:
        """
        Finds all organizations at a specific hierarchical depth.
        """
        with self.db.get_cursor() as cur:
            cur.execute(
                "SELECT * FROM find_organizations_by_depth(%s)", (depth,)
            )
            return [self._row_to_dict(row) for row in cur.fetchall()]

    def get_timeline_dates_for_subtree(
        self, parent_org_id: int
    ) -> List[str]:
        """
        Finds all unique 'first_observed' and 'last_observed' dates for an
        organization and all its descendants. These dates represent points
        in time where the organizational structure changed.

        Returns a sorted list of dates in ISO format (YYYY-MM-DD).
        """
        with self.db.get_cursor() as cur:
            # This query first finds the entire subtree, then unnests the
            # relevant dates, gets the unique set, and sorts them.
            cur.execute(
                """
                WITH RECURSIVE org_subtree AS (
                    -- Anchor member: the starting parent organization
                    SELECT id, metadata FROM organizations WHERE id = %(parent_id)s
                    UNION ALL
                    -- Recursive member: join to find children
                    SELECT o.id, o.metadata FROM organizations o
                    JOIN org_subtree s ON o.parent_org_id = s.id
                ),
                all_event_dates AS (
                    -- Get all 'first_observed' dates from the subtree
                    SELECT (metadata->>'first_observed')::date AS event_date
                    FROM org_subtree
                    WHERE metadata->>'first_observed' IS NOT NULL
                    UNION -- UNION implicitly performs a DISTINCT
                    -- Get all 'last_observed' dates from the subtree
                    SELECT (metadata->>'last_observed')::date AS event_date
                    FROM org_subtree
                    WHERE metadata->>'last_observed' IS NOT NULL
                )
                SELECT event_date
                FROM all_event_dates
                ORDER BY event_date ASC;
                """,
                {"parent_id": parent_org_id},
            )
            # Fetch all rows and flatten the list of tuples into a list of strings
            return [row["event_date"].isoformat() for row in cur.fetchall()]

    def get_org_descendants_diff_between_dates(
        self,
        parent_org_id: int,
        start_date: str,
        end_date: str,
    ) -> List[Dict[str, Any]]:
        """
        Get a summary of changes in the organization structure between two dates.
        This function returns a list of dictionaries, each containing the
        organization ID, name, and a list of changes (added, removed, or unchanged).
        """
        with self.db.get_cursor() as cur:
            cur.execute(
                """
                SELECT * FROM get_org_descendants_diff(%s, %s, %s);
                """,
                (parent_org_id, start_date, end_date),
            )
            return [self._row_to_dict(row) for row in cur.fetchall()]

    def update_parent_link(
        self, org_id: int, parent_org_id: Optional[int]
    ) -> bool:
        """Update the parent_org_id for a specific organization."""
        with self.db.get_cursor() as cur:
            cur.execute(
                """
                UPDATE organizations
                SET parent_org_id = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING id;
            """,
                (parent_org_id, org_id),
            )
            return cur.fetchone() is not None

    def get_org_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the organizations in the database.
        Returns a dictionary with counts of total organizations,
        unique departments, and other relevant metrics.
        """
        with self.db.get_cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS total_orgs,
                       COUNT(DISTINCT department) AS unique_departments
                FROM organizations;
                """
            )
            result = cur.fetchone()
            return (
                {
                    "total_organizations": result["total_orgs"],
                    "unique_departments": result["unique_departments"],
                }
                if result
                else {}
            )
