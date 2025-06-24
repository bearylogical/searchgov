# repositories/people_repository.py
from .base import BaseRepository
from typing import List, Dict, Any, Optional
import json

# Default similarity threshold for fuzzy matching in this repository
DEFAULT_MIN_SIMILARITY_THRESHOLD_REPO = 0.3


class PeopleRepository(BaseRepository):
    async def create(self, data: Dict[str, Any]) -> Optional[int]:
        """Create or update a person record"""
        async with self.db.acquire() as conn:
            disambiguation_key = data.get("disambiguation_key", 1)

            result = await conn.fetchrow(
                """
                INSERT INTO people (name, clean_name, tel, email, disambiguation_key, metadata)
                VALUES ($1, $2, $3, $4, $5, $6)
                -- MODIFIED: The conflict target is now the composite key
                ON CONFLICT (name, disambiguation_key) DO UPDATE SET
                    clean_name = EXCLUDED.clean_name,
                    tel = COALESCE(EXCLUDED.tel, people.tel),
                    email = COALESCE(EXCLUDED.email, people.email),
                    metadata = people.metadata || EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id;
            """,
                data["name"],
                data["clean_name"],
                data.get("tel"),
                data.get("email"),
                disambiguation_key,
                json.dumps(data.get("metadata", {})),
            )
            return result["id"] if result else None

    async def find_by_person_id(self, id: int) -> Optional[Dict[str, Any]]:
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM people WHERE id = $1", id
            )
            return dict(row) if row else None

    async def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        # This remains for exact, single-record lookups
        async with self.db.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT * FROM people WHERE name = $1", name
            )
            return dict(result) if result else None

    async def search_by_name_fuzzy(
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
            async with self.db.acquire() as conn:
                # Attempt trigram similarity search
                # The 'name % $1' condition helps leverage GIN/GiST trigram indexes.
                # The 'similarity(name, $1) >= $2' is the actual threshold filter.
                results = await conn.fetch(
                    """
                    SELECT *, similarity(name::text, $1) as sim_score
                    FROM people
                    WHERE name::text % $1 AND similarity(name::text, $1) >= $2
                    ORDER BY sim_score DESC
                    LIMIT $3;
                    """,
                    name_query,
                    min_similarity_threshold,
                    limit,
                )
                return [dict(row) for row in results]
        except Exception as e:
            # psycopg2.errors.UndefinedFunction (SQLSTATE 42883) indicates
            # pg_trgm functions (similarity, %) are not available.
            if hasattr(e, "pgcode") and e.pgcode == "42883":
                # Consider adding logging here if a logger is part of BaseRepository
                # For example: self.logger.warning(f"pg_trgm not available for '{name_query}'. Falling back to ILIKE.")
                async with self.db.acquire() as conn_fallback:
                    rows = await conn_fallback.fetch(
                        """
                        SELECT *, 0.0 as sim_score -- Provide a dummy sim_score for API consistency
                        FROM people
                        WHERE name ILIKE $1
                        ORDER BY length(name) ASC, name ASC -- Basic ordering for ILIKE
                        LIMIT $2;
                        """,
                        f"%{name_query}%",
                        limit,
                    )
                    return [dict(row) for row in rows]
            else:
                # For other unexpected database errors, re-raise to allow higher-level handling.
                # Consider logging the error here as well.
                # For example: self.logger.error(f"DB error during fuzzy search for '{name_query}': {e}")
                raise
        # This path should ideally not be reached if exceptions are properly handled/re-raised.
        return []

    async def search_by_name_fuzzy_with_time_range(
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
            async with self.db.acquire() as conn:
                results = await conn.fetch(
                    """
                    SELECT *, similarity(name::text, $1) as sim_score
                    FROM people
                    WHERE name::text % $1
                        AND similarity(name::text, $1) >= $2
                        AND created_at >= $3
                        AND created_at <= $4
                    ORDER BY sim_score DESC
                    LIMIT $5;
                    """,
                    name_query,
                    min_similarity_threshold,
                    start_date,
                    end_date,
                    limit,
                )
                return [dict(row) for row in results]
        except Exception as e:
            if hasattr(e, "pgcode") and e.pgcode == "42883":
                async with self.db.acquire() as conn_fallback:
                    rows = await conn_fallback.fetch(
                        """
                        SELECT *, 0.0 as sim_score -- Provide a dummy sim_score for API consistency
                        FROM people
                        WHERE name ILIKE $1
                            AND created_at >= $2
                            AND created_at <= $3
                        ORDER BY length(name) ASC, name ASC -- Basic ordering for ILIKE
                        LIMIT $4;
                        """,
                        f"%{name_query}%",
                        start_date,
                        end_date,
                        limit,
                    )
                    return [dict(row) for row in rows]
            else:
                raise

    async def search_by_name_embedding(
        self, embedding: List[float], limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search by embedding similarity"""
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SET LOCAL ivfflat.probes = 10;")
                rows = await conn.fetch(
                    """
                    SELECT *, 1 - (embedding <=> $1) as distance
                    FROM people
                    WHERE embedding IS NOT NULL
                    ORDER BY distance DESC
                    LIMIT $2
                """,
                    embedding,
                    limit,
                )
                return [dict(row) for row in rows]

    async def search_by_name_fts(
        self, query_string: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Full-text search on the name column using tsvector."""
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH search_query AS (
                    SELECT plainto_tsquery('english', $1) AS q
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
                LIMIT $2;
            """,
                query_string,
                limit,
            )
            return [dict(row) for row in rows]

    async def get_name_stats(self) -> Dict[str, Any]:
        """Get statistics about names in the people table."""
        async with self.db.acquire() as conn:
            result = await conn.fetchrow(
                """
                SELECT
                    COUNT(DISTINCT name) AS unique_names,
                FROM
                    people;
            """
            )
            return (
                {
                    "unique_names": result["unique_names"],
                }
                if result
                else {}
            )
