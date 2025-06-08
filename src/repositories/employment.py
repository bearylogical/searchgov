# src/repositories/employment.py
from .base import BaseRepository
from typing import List, Dict, Any, Optional
import json
import logging


class EmploymentRepository(BaseRepository):
    def __init__(self, db_connection):
        super().__init__(db_connection)
        self.logger = logging.getLogger(__name__)

    def create(self, data: Dict[str, Any]) -> Optional[int]:
        """
        Create an employment record.
        If an exact duplicate (based on person_id, org_id, rank, start_date, end_date) exists,
        it updates specified fields (tenure_days, raw_name, metadata).
        Returns the ID of the inserted or updated record.
        """
        with self.db.get_cursor() as cur:
            params = {
                "person_id": data["person_id"],
                "org_id": data["org_id"],
                "rank": data.get("rank"),
                "start_date": data["start_date"],
                "end_date": data["end_date"],
                "tenure_days": data.get("tenure_days"),
                "raw_name": data.get("raw_name", ""),
                "metadata": json.dumps(data.get("metadata", {})),
            }

            # The conflict target (person_id, org_id, (COALESCE(rank, ''::character varying)), start_date, end_date)
            # must exactly match the definition of your unique index.
            # The ::character varying cast for the COALESCE expression ensures type matching.
            sql = """
                INSERT INTO employment (
                    person_id, org_id, rank, start_date, end_date, 
                    tenure_days, raw_name, metadata
                )
                VALUES (
                    %(person_id)s, %(org_id)s, %(rank)s, %(start_date)s, %(end_date)s,
                    %(tenure_days)s, %(raw_name)s, %(metadata)s
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
                cur.execute(sql, params)
                result = cur.fetchone()
                return result["id"] if result else None
            except Exception as e:
                self.logger.error(
                    f"Error in EmploymentRepository.create for person_id {data.get('person_id')}, org_id {data.get('org_id')}: {e}",
                    exc_info=True,
                )
                raise

    def find_by_id(
        self, record_id: int
    ) -> Optional[Dict[str, Any]]:  # Renamed id to record_id
        with self.db.get_cursor() as cur:
            cur.execute(
                """
                SELECT e.*, p.name as person_name, o.name as org_name
                FROM employment e
                JOIN people p ON e.person_id = p.id
                JOIN organizations o ON e.org_id = o.id
                WHERE e.id = %s
            """,
                (record_id,),
            )
            result = cur.fetchone()
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

    def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        # Not applicable for employment
        raise NotImplementedError(
            "Employment doesn't have a single name field"
        )

    def find_by_person_and_org(
        self, person_id: int, org_id: int
    ) -> List[Dict[str, Any]]:
        """Find all employment records for a person at an organization"""
        with self.db.get_cursor() as cur:
            cur.execute(
                """
                SELECT * FROM employment 
                WHERE person_id = %s AND org_id = %s
                ORDER BY start_date
            """,
                (person_id, org_id),
            )
            results = []
            for row in cur.fetchall():
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
