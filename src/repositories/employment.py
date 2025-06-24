# src/repositories/employment.py
from .base import BaseRepository
from typing import List, Dict, Any, Optional, Union
import json


class EmploymentRepository(BaseRepository):
    def __init__(self, db_connection):
        super().__init__(db_connection)

    async def create(self, data: Dict[str, Any]) -> Optional[int]:
        """
        Create an employment record.
        If an exact duplicate (based on person_id, org_id, rank, start_date, end_date) exists,
        it updates specified fields (tenure_days, raw_name, metadata).
        Returns the ID of the inserted or updated record.
        """
        async with self.db.acquire() as conn:
            # The conflict target (person_id, org_id, (COALESCE(rank, ''::character varying)), start_date, end_date)
            # must exactly match the definition of your unique index.
            # The ::character varying cast for the COALESCE expression ensures type matching.
            sql = """
                INSERT INTO employment (
                    person_id, org_id, rank, start_date, end_date, 
                    tenure_days, raw_name, metadata
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8
                )
                ON CONFLICT (person_id, org_id, (COALESCE(rank, ''::character varying)), start_date, end_date)
                DO UPDATE SET
                    tenure_days = COALESCE(EXCLUDED.tenure_days, employment.tenure_days),
                    raw_name = COALESCE(EXCLUDED.raw_name, employment.raw_name),
                    metadata = employment.metadata || EXCLUDED.metadata
                    -- If you add an 'updated_at' column to the employment table:
                    -- , updated_at = CURRENT_TIMESTAMP 
                RETURNING id;
            """
            try:
                result = await conn.fetchrow(
                    sql,
                    data["person_id"],
                    data["org_id"],
                    data.get("rank"),
                    data["start_date"],
                    data["end_date"],
                    data.get("tenure_days"),
                    data.get("raw_name", ""),
                    json.dumps(data.get("metadata", {})),
                )
                return result["id"] if result else None
            except Exception as e:
                self.logger.error(
                    f"Error in EmploymentRepository.create for person_id {data.get('person_id')}, org_id {data.get('org_id')}: {e}",
                    exc_info=True,
                )
                raise

    async def find_by_employment_id(
        self, record_id: int
    ) -> Optional[Dict[str, Any]]:  # Renamed id to record_id
        async with self.db.acquire() as conn:
            result = await conn.fetchrow(
                """
                SELECT e.*, p.name as person_name, o.name as org_name
                FROM employment e
                JOIN people p ON e.person_id = p.id
                JOIN organizations o ON e.org_id = o.id
                WHERE e.id = $1
            """,
                record_id,
            )
            if result:
                res_dict = dict(result)
                if isinstance(res_dict.get("metadata"), str):
                    try:
                        res_dict["metadata"] = json.loads(
                            res_dict["metadata"]
                        )
                    except json.JSONDecodeError:
                        self.logger.warning(
                            f"Could not decode metadata for employment id {record_id}"
                        )
                return res_dict
            return None

    async def find_by_person_id(
        self, person_id: int
    ) -> List[Dict[str, Any]]:
        """Find all employment records for a person"""
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT e.*, p.name as person_name, o.name as org_name, o.metadata as org_metadata, o.id as org_id
                FROM employment e
                JOIN people p ON e.person_id = p.id
                JOIN organizations o ON e.org_id = o.id
                WHERE e.person_id = $1
                ORDER BY e.start_date
            """,
                person_id,
            )
            results = []
            for row in rows:
                res_dict = dict(row)
                if isinstance(res_dict.get("metadata"), str):
                    try:
                        res_dict["metadata"] = json.loads(
                            res_dict["metadata"]
                        )
                    except json.JSONDecodeError:
                        self.logger.warning(
                            f"Could not decode metadata for employment with person_id {person_id}"
                        )
                results.append(res_dict)
            return results

    def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        # Not applicable for employment
        raise NotImplementedError(
            "Employment doesn't have a single name field"
        )

    async def find_by_person_and_org(
        self, person_id: int, org_id: int
    ) -> List[Dict[str, Any]]:
        """Find all employment records for a person at an organization"""
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM employment 
                WHERE person_id = $1 AND org_id = $2
                ORDER BY start_date
            """,
                person_id,
                org_id,
            )
            results = []
            for row in rows:
                res_dict = dict(row)
                if isinstance(res_dict.get("metadata"), str):
                    try:
                        res_dict["metadata"] = json.loads(
                            res_dict["metadata"]
                        )
                    except json.JSONDecodeError:
                        self.logger.warning(
                            f"Could not decode metadata for employment with person_id {person_id}, org_id {org_id}"
                        )
                results.append(res_dict)
            return results

    async def find_most_recent_end_date(self) -> Optional[str]:
        """Get the most recent end date across all employment records"""
        async with self.db.acquire() as conn:
            result = await conn.fetchrow(
                """
                SELECT MAX(end_date) as most_recent_end_date
                FROM employment
            """
            )
            if result and result["most_recent_end_date"]:
                return result["most_recent_end_date"].isoformat()
            return None

    async def find_people_with_overlapping_employment(
        self,
        person_ids: Union[int, List[int]],
        name_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Finds unique person/employment records connected to a given person or
        list of people by working in the same organization or its hierarchy
        during an overlapping time period.

        A person may appear multiple times if they have multiple distinct
        overlapping employments.

        Args:
            person_ids: The ID or list of IDs of the source person(s).
            name_filter: If provided, filters the results for people with a
                        matching name (case-insensitive, wildcard). The limit
                        is ignored when this is used.
            limit: The max number of records to return if name_filter is not used.

        Returns:
            A list of dictionaries, each with the 'id', 'name', 'start_date',
            and 'end_date' of a person's overlapping employment.
        """
        # Normalize input to a list and handle empty case
        if isinstance(person_ids, int):
            source_person_ids = [person_ids]
        else:
            source_person_ids = person_ids

        if not source_person_ids:
            return []

        async with self.db.acquire() as conn:
            # This query is complex, so let's break it down with CTEs:
            # 1. `source_employments`: Gathers all employment records for the
            #    input person(s).
            # 2. `descendant_orgs`: Recursively finds all organizations that are
            #    children, grandchildren, etc., of the source employment orgs.
            # 3. `ancestor_orgs`: Recursively finds all parent, grandparent,
            #    etc., organizations.
            # 4. `org_family`: Combines the source orgs, their ancestors, and
            #    their descendants into a single set of relevant organizations.
            # 5. Final SELECT: Finds other people who worked in the `org_family`
            #    during an overlapping time period, excluding the source people.
            sql = """
                WITH RECURSIVE
                source_employments AS (
                    SELECT org_id, start_date, end_date
                    FROM employment
                    WHERE person_id = ANY($1)
                ),
                descendant_orgs AS (
                    -- Base case: Orgs where the source people worked
                    SELECT id FROM organizations
                    WHERE id IN (SELECT org_id FROM source_employments)
                    UNION ALL
                    -- Recursive step: Children of orgs already found
                    SELECT o.id FROM organizations o
                    JOIN descendant_orgs d ON o.parent_org_id = d.id
                ),
                ancestor_orgs AS (
                    -- Base case: Orgs where the source people worked
                    SELECT id, parent_org_id FROM organizations
                    WHERE id IN (SELECT org_id FROM source_employments)
                    UNION ALL
                    -- Recursive step: Parents of orgs already found
                    SELECT o.id, o.parent_org_id FROM organizations o
                    JOIN ancestor_orgs a ON o.id = a.parent_org_id
                ),
                org_family AS (
                    -- Combine all related orgs, removing duplicates
                    SELECT id FROM descendant_orgs
                    UNION
                    SELECT id FROM ancestor_orgs
                )
                -- Final selection of people with overlapping employment
                SELECT DISTINCT
                    p.id,
                    p.name,
                    e2.start_date,
                    e2.end_date
                FROM people p
                JOIN employment e2 ON p.id = e2.person_id
                WHERE
                    -- Exclude the source person(s) from the results
                    p.id <> ALL($1)
                    -- Filter to employments within the same org hierarchy
                    AND e2.org_id IN (SELECT id FROM org_family)
                    -- Check for any time overlap with any of the source employments
                    AND EXISTS (
                        SELECT 1
                        FROM source_employments e1
                        WHERE daterange(e1.start_date, e1.end_date, '[]') &&
                              daterange(e2.start_date, e2.end_date, '[]')
                    )
            """
            # Parameters for the query.
            params = [source_person_ids]

            # Dynamically add the name filter if it exists
            if name_filter:
                sql += f" AND p.name ILIKE ${len(params) + 1}"
                params.append(f"%{name_filter}%")

            # Always order for consistent results.
            sql += " ORDER BY p.name ASC, e2.start_date ASC"

            # Only apply the limit if we are NOT filtering by name
            if not name_filter:
                sql += f" LIMIT ${len(params) + 1}"
                params.append(limit)

            # self.logger.debug(
            #     "Executing find_people_with_overlapping_employment with params: "
            #     f"{params} and SQL: {sql}"
            # )
            rows = await conn.fetch(sql, *params)
            return [dict(row) for row in rows]

    async def get_employment_stats(self) -> Dict[str, Any]:
        """
        Get statistics about employment records.
        Returns a dictionary with counts and other relevant stats.
        """
        async with self.db.acquire() as conn:
            result = await conn.fetchrow(
                """
                SELECT COUNT(*) AS total_employments,
                       COUNT(DISTINCT person_id) AS total_people,
                       COUNT(DISTINCT org_id) AS total_organizations
                FROM employment
            """
            )
            if result:
                return {
                    "total_employments": result["total_employments"],
                    "total_people": result["total_people"],
                    "total_organizations": result["total_organizations"],
                }
