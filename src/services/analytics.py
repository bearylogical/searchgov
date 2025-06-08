from typing import List, Dict, Any
from src.database.postgres.connection import DatabaseConnection
import logging


class AnalyticsService:
    def __init__(self, db_connection: DatabaseConnection):
        self.db = db_connection
        self.logger = logging.getLogger(__name__)

    def analyze_organization_turnover(
        self, org_name: str, start_date: str = None, end_date: str = None
    ) -> Dict:
        """Analyze turnover patterns"""
        try:
            with self.db.get_cursor() as cur:
                date_filter = ""
                params = [org_name]

                if start_date and end_date:
                    date_filter = (
                        "AND e.start_date >= %s AND e.end_date <= %s"
                    )
                    params.extend([start_date, end_date])

                query = f"""
                    SELECT 
                        p.name as employee_name,
                        e.rank,
                        e.start_date,
                        e.end_date,
                        e.tenure_days
                    FROM employment e
                    JOIN people p ON e.person_id = p.id
                    JOIN organizations o ON e.org_id = o.id
                    WHERE o.name = %s
                    {date_filter}
                    ORDER BY e.start_date
                """

                cur.execute(query, params)
                employees = [dict(row) for row in cur.fetchall()]

                if employees:
                    tenure_days = [
                        emp["tenure_days"]
                        for emp in employees
                        if emp["tenure_days"]
                    ]
                    avg_tenure = (
                        sum(tenure_days) / len(tenure_days)
                        if tenure_days
                        else 0
                    )

                    return {
                        "organization": org_name,
                        "total_employees": len(employees),
                        "avg_tenure_days": avg_tenure,
                        "employees": employees,
                    }

                return {"organization": org_name, "total_employees": 0}

        except Exception as e:
            self.logger.error(f"Error analyzing turnover: {e}")
            return {"error": str(e)}

    def find_succession_patterns(
        self, max_gap_days: int = 90
    ) -> List[Dict]:
        """Find succession patterns"""
        try:
            with self.db.get_cursor() as cur:
                cur.execute(
                    """
                    SELECT 
                        o.name as organization,
                        e1.rank as role,
                        p1.name as predecessor,
                        p2.name as successor,
                        e1.end_date as predecessor_end,
                        e2.start_date as successor_start,
                        e2.start_date - e1.end_date as gap_days
                    FROM employment e1
                    JOIN employment e2 ON e1.org_id = e2.org_id AND e1.rank = e2.rank
                    JOIN people p1 ON e1.person_id = p1.id
                    JOIN people p2 ON e2.person_id = p2.id
                    JOIN organizations o ON e1.org_id = o.id
                    WHERE p1.name != p2.name
                    AND e2.start_date > e1.end_date
                    AND e2.start_date - e1.end_date <= %s
                    ORDER BY gap_days
                """,
                    (max_gap_days,),
                )

                return [dict(row) for row in cur.fetchall()]

        except Exception as e:
            self.logger.error(f"Error finding succession patterns: {e}")
            return []
