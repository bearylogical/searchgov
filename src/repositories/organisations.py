from .base import BaseRepository
from typing import Dict, Any, Optional
import json


class OrganisationsRepository(BaseRepository):
    def create(self, data: Dict[str, Any]) -> Optional[int]:
        """
        Create or update an organization record.
        Expects 'parent_org_id' in data if a parent link is to be set.
        """
        with self.db.get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, department, url, parent_org_id, metadata) 
                VALUES (%(name)s, %(department)s, %(url)s, %(parent_org_id)s, %(metadata)s)
                ON CONFLICT (name) DO UPDATE SET
                    department = COALESCE(EXCLUDED.department, organizations.department),
                    url = COALESCE(EXCLUDED.url, organizations.url),
                    parent_org_id = COALESCE(EXCLUDED.parent_org_id, organizations.parent_org_id),
                    metadata = organizations.metadata || EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id;
            """,
                {
                    "name": data["name"],
                    "department": data.get("department"),
                    "url": data.get("url"),
                    "parent_org_id": data.get(
                        "parent_org_id"
                    ),  # Get parent_org_id
                    "metadata": json.dumps(data.get("metadata", {})),
                },
            )

            result = cur.fetchone()
            return result["id"] if result else None

    def find_by_id(self, org_id: int) -> Optional[Dict[str, Any]]:
        """Find an organization by its ID."""
        with self.db.get_cursor() as cur:
            cur.execute(
                "SELECT * FROM organizations WHERE id = %s", (org_id,)
            )
            result = cur.fetchone()
            if result:
                # Convert metadata back to dict if it's a string
                org_data = dict(result)
                if isinstance(org_data.get("metadata"), str):
                    try:
                        org_data["metadata"] = json.loads(
                            org_data["metadata"]
                        )
                    except json.JSONDecodeError:
                        self.logger.warning(
                            f"Could not decode metadata for org_id {org_id}"
                        )
                return org_data
            return None

    def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Find an organization by its name."""
        with self.db.get_cursor() as cur:
            cur.execute(
                "SELECT * FROM organizations WHERE name = %s", (name,)
            )
            result = cur.fetchone()
            if result:
                org_data = dict(result)
                if isinstance(org_data.get("metadata"), str):
                    try:
                        org_data["metadata"] = json.loads(
                            org_data["metadata"]
                        )
                    except json.JSONDecodeError:
                        self.logger.warning(
                            f"Could not decode metadata for org name {name}"
                        )
                return org_data
            return None

    def find_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Find an organization by its URL."""
        with self.db.get_cursor() as cur:
            cur.execute(
                "SELECT * FROM organizations WHERE url = %s", (url,)
            )
            result = cur.fetchone()
            if result:
                org_data = dict(result)
                if isinstance(org_data.get("metadata"), str):
                    try:
                        org_data["metadata"] = json.loads(
                            org_data["metadata"]
                        )
                    except json.JSONDecodeError:
                        self.logger.warning(
                            f"Could not decode metadata for org url {url}"
                        )
                return org_data
            return None

    def get_children(self, parent_org_id: int) -> list[Dict[str, Any]]:
        """Get all direct children of a given parent organization."""
        children = []
        with self.db.get_cursor() as cur:
            cur.execute(
                "SELECT * FROM organizations WHERE parent_org_id = %s ORDER BY name",
                (parent_org_id,),
            )
            for row in cur.fetchall():
                child_data = dict(row)
                if isinstance(child_data.get("metadata"), str):
                    try:
                        child_data["metadata"] = json.loads(
                            child_data["metadata"]
                        )
                    except json.JSONDecodeError:
                        self.logger.warning(
                            f"Could not decode metadata for child org_id {child_data['id']}"
                        )
                children.append(child_data)
        return children

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
