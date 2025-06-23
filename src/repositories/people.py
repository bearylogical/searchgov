# repositories/people_repository.py
from .base import BaseRepository
from typing import List, Dict, Any, Optional
import json

# Default similarity threshold for fuzzy matching in this repository
DEFAULT_MIN_SIMILARITY_THRESHOLD_REPO = 0.3


class PeopleRepository(BaseRepository):
    def create(self, data: Dict[str, Any]) -> Optional[int]:
        """Create or update a person record"""
        with self.db.get_cursor() as cur:
            disambiguation_key = data.get("disambiguation_key", 1)

            cur.execute(
                """
                INSERT INTO people (name, clean_name, tel, email, disambiguation_key, metadata)
                VALUES (%(name)s, %(clean_name)s, %(tel)s, %(email)s, %(disambiguation_key)s, %(metadata)s)
                -- MODIFIED: The conflict target is now the composite key
                ON CONFLICT (name, disambiguation_key) DO UPDATE SET
                    clean_name = EXCLUDED.clean_name,
                    tel = COALESCE(EXCLUDED.tel, people.tel),
                    email = COALESCE(EXCLUDED.email, people.email),
                    metadata = people.metadata || EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id;
            """,
                {
                    "name": data["name"],
                    "clean_name": data["clean_name"],
                    "tel": data.get("tel"),
                    "email": data.get("email"),
                    "disambiguation_key": disambiguation_key,
                    "metadata": json.dumps(data.get("metadata", {})),
                },
            )
            result = cur.fetchone()
            return result["id"] if result else None

    def find_by_person_id(self, id: int) -> Optional[Dict[str, Any]]:
        with self.db.get_cursor() as cur:
            cur.execute("SELECT * FROM people WHERE id = %s", (id,))
            row = cur.fetchone()  # Fetch once
            return dict(row) if row else None

    def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        # This remains for exact, single-record lookups
        with self.db.get_cursor() as cur:
            cur.execute("SELECT * FROM people WHERE name = %s", (name,))
            result = cur.fetchone()  # Fetch once
            return dict(result) if result else None

    def search_by_name_fuzzy(
        self,
        name_query: str,
        limit: int = 10,
        min_similarity_threshold: float = DEFAULT_MIN_SIMILARITY_THRESHOLD_REPO,
    ) -> List[Dict[str, Any]]:
        """
        Fuzzy search for people by name using trigram similarity.
        Returns a list of people records, each including a 'sim_score'.
        Falls back to ILIKE if the pg_trgm extension is not available.
        Requires the pg_trgm extension to be enabled in PostgreSQL for trigram search.
        """
        try:
            with self.db.get_cursor() as cur:
                # Attempt trigram similarity search
                # The 'name %% %(name_query)s' condition helps leverage GIN/GiST trigram indexes.
                # The 'similarity(name, %(name_query)s) >= %(threshold)s' is the actual threshold filter.
                cur.execute(
                    """
                    SELECT *, similarity(name, %(name_query)s) as sim_score
                    FROM people
                    WHERE name %% %(name_query)s AND similarity(name, %(name_query)s) >= %(threshold)s
                    ORDER BY sim_score DESC
                    LIMIT %(limit)s;
                    """,
                    {
                        "name_query": name_query,
                        "threshold": min_similarity_threshold,
                        "limit": limit,
                    },
                )
                results = [dict(row) for row in cur.fetchall()]
                return results
        except Exception as e:
            # psycopg2.errors.UndefinedFunction (SQLSTATE 42883) indicates
            # pg_trgm functions (similarity, %%) are not available.
            if hasattr(e, "pgcode") and e.pgcode == "42883":
                # Consider adding logging here if a logger is part of BaseRepository
                # For example: self.logger.warning(f"pg_trgm not available for '{name_query}'. Falling back to ILIKE.")
                with self.db.get_cursor() as cur_fallback:
                    cur_fallback.execute(
                        """
                        SELECT *, 0.0 as sim_score -- Provide a dummy sim_score for API consistency
                        FROM people
                        WHERE name ILIKE %(name_query_like)s
                        ORDER BY length(name) ASC, name ASC -- Basic ordering for ILIKE
                        LIMIT %(limit)s;
                        """,
                        {
                            "name_query_like": f"%{name_query}%",
                            "limit": limit,
                        },
                    )
                    return [dict(row) for row in cur_fallback.fetchall()]
            else:
                # For other unexpected database errors, re-raise to allow higher-level handling.
                # Consider logging the error here as well.
                # For example: self.logger.error(f"DB error during fuzzy search for '{name_query}': {e}")
                raise
        # This path should ideally not be reached if exceptions are properly handled/re-raised.
        return []

    def search_by_name_fuzzy_with_time_range(
        self,
        name_query: str,
        start_date: str,
        end_date: str,
        limit: int = 10,
        min_similarity_threshold: float = DEFAULT_MIN_SIMILARITY_THRESHOLD_REPO,
    ) -> List[Dict[str, Any]]:
        """
        Fuzzy search for people by name within a specific time range using trigram similarity.
        Returns a list of people records, each including a 'sim_score'.
        Falls back to ILIKE if the pg_trgm extension is not available.
        Requires the pg_trgm extension to be enabled in PostgreSQL for trigram search.
        """
        try:
            with self.db.get_cursor() as cur:
                cur.execute(
                    """
                    SELECT *, similarity(name, %(name_query)s) as sim_score
                    FROM people
                    WHERE name %% %(name_query)s
                        AND similarity(name, %(name_query)s) >= %(threshold)s
                        AND created_at >= %(start_date)s
                        AND created_at <= %(end_date)s
                    ORDER BY sim_score DESC
                    LIMIT %(limit)s;
                    """,
                    {
                        "name_query": name_query,
                        "threshold": min_similarity_threshold,
                        "start_date": start_date,
                        "end_date": end_date,
                        "limit": limit,
                    },
                )
                results = [dict(row) for row in cur.fetchall()]
                return results
        except Exception as e:
            if hasattr(e, "pgcode") and e.pgcode == "42883":
                with self.db.get_cursor() as cur_fallback:
                    cur_fallback.execute(
                        """
                        SELECT *, 0.0 as sim_score -- Provide a dummy sim_score for API consistency
                        FROM people
                        WHERE name ILIKE %(name_query_like)s
                            AND created_at >= %(start_date)s
                            AND created_at <= %(end_date)s
                        ORDER BY length(name) ASC, name ASC -- Basic ordering for ILIKE
                        LIMIT %(limit)s;
                        """,
                        {
                            "name_query_like": f"%{name_query}%",
                            "start_date": start_date,
                            "end_date": end_date,
                            "limit": limit,
                        },
                    )
                    return [dict(row) for row in cur_fallback.fetchall()]
            else:
                raise

    def search_by_name_embedding(
        self, embedding: List[float], limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search by embedding similarity"""
        with self.db.get_cursor() as cur:
            cur.execute(
                """
                SET LOCAL ivfflat.probes = 10;
                SELECT *, 1 - (embedding <=> %s) as distance
                FROM people 
                WHERE embedding IS NOT NULL
                ORDER BY distance DESC
                LIMIT %s
            """,
                (embedding, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    def search_by_name_fts(
        self, query_string: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Full-text search on the name column using tsvector."""
        with self.db.get_cursor() as cur:
            cur.execute(
                """
                WITH search_query AS (
                    SELECT plainto_tsquery('english', %s) AS q
                )
                SELECT
                    p.*,
                    ts_rank_cd(
                        to_tsvector('english', p.name), sq.q
                    ) AS fts_rank
                FROM
                    people p, search_query sq
                WHERE
                    p.name IS NOT NULL AND
                    to_tsvector('english', p.name) @@ sq.q
                ORDER BY
                    fts_rank DESC
                LIMIT %s;
            """,
                (query_string, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_name_stats(self) -> Dict[str, Any]:
        """Get statistics about names in the people table."""
        with self.db.get_cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(DISTINCT name) AS unique_names,
                FROM
                    people;
            """
            )
            result = cur.fetchone()
            return (
                {
                    "unique_names": result["unique_names"],
                }
                if result
                else {}
            )
