# database/schema.py
from .connection import DatabaseConnection
from pgvector.psycopg2 import register_vector
from loguru import logger


class SchemaManager:
    def __init__(self, db_connection: DatabaseConnection):
        self.db = db_connection
        self.logger = logger

    def setup_schema(self):
        """Create complete database schema"""
        with self.db.transaction():
            self._create_extensions()
            self._create_tables()
            self._create_indexes()
            self._create_materialized_views()
            self._create_functions()

    def reset_schema(self):
        """Reset the database schema by dropping all tables and recreating them"""
        with self.db.transaction():
            self._drop_tables()
            self._create_extensions()
            self._create_tables()
            self._create_indexes()
            self._create_materialized_views()
            self._create_functions()

    def _drop_tables(self):
        """Drop all tables in the schema"""
        with self.db.get_cursor() as cur:
            tables = [
                "employment",
                "people",
                "organizations",
                "colleague_pairs",
                # Materialized view, will be dropped with CASCADE from dependent tables or explicitly
            ]

            # Drop materialized view first if it exists and is not dropped by CASCADE
            cur.execute("DROP MATERIALIZED VIEW IF EXISTS colleague_pairs;")
            self.logger.debug("Dropped materialized view: colleague_pairs")

            for table in tables:
                # Ensure we only try to drop actual tables that might exist
                if table != "colleague_pairs":
                    cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                    self.logger.debug(f"Dropped table: {table}")

            self.logger.info("All tables and materialized views dropped")
            # self.db.conn.commit() # Commit is handled by the transaction context manager
            # self.logger.info("Database schema reset complete") # Moved to end of reset_schema

    def _create_extensions(self):
        """Enable required PostgreSQL extensions"""
        with self.db.get_cursor() as cur:
            extensions = [
                "CREATE EXTENSION IF NOT EXISTS btree_gist;",
                "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
                "CREATE EXTENSION IF NOT EXISTS vector;",
            ]

            for ext in extensions:
                cur.execute(ext)
                self.logger.debug(f"Created extension: {ext}")

        self.logger.info("Registered vector extension")
        self.register_pgvector()

    def register_pgvector(self):
        with self.db.get_cursor() as cur:
            register_vector(cur.connection)

    def _create_tables(self):
        """Create all tables"""
        with self.db.get_cursor() as cur:
            # People table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS people (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(500) NOT NULL, -- UNIQUE constraint removed from here
                    clean_name VARCHAR(500) NOT NULL,
                    tel VARCHAR(50),
                    email VARCHAR(320),
                    disambiguation_key INTEGER NOT NULL DEFAULT 1,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Organizations table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS organizations (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(1000)  NOT NULL,
                    department VARCHAR(500),
                    url VARCHAR(1000) UNIQUE,
                    parent_org_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL, -- Added parent org link
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            self.logger.info(
                "Created organizations table with parent_org_id"
            )

            # Employment table with temporal constraints
            cur.execute("""
                CREATE TABLE IF NOT EXISTS employment (
                    id SERIAL PRIMARY KEY,
                    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
                    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                    rank VARCHAR(500),
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    tenure_days INTEGER,
                    raw_name VARCHAR(500),
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    CONSTRAINT valid_date_range CHECK (start_date <= end_date)
                );
            """)

            cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_employment_exact_duplicate
            ON employment (person_id, org_id, COALESCE(rank, ''), start_date, end_date);
            """)

            cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_people_unique_person
            ON people(name, disambiguation_key);
            """)

            self.logger.info("Database tables created")

    def _create_indexes(self):
        """Create all indexes for optimal performance"""
        with self.db.get_cursor() as cur:
            indexes = [
                # People indexes
                "CREATE INDEX IF NOT EXISTS idx_people_name ON people(name);",
                "CREATE INDEX IF NOT EXISTS idx_people_clean_name ON people(clean_name);",
                "CREATE INDEX IF NOT EXISTS idx_people_tel ON people(tel) WHERE tel IS NOT NULL;",
                "CREATE INDEX IF NOT EXISTS idx_people_name_trgm ON people USING gin(name gin_trgm_ops);",
                # Organizations indexes
                "CREATE INDEX IF NOT EXISTS idx_org_name ON organizations(name);",
                "CREATE INDEX IF NOT EXISTS idx_org_name_trgm ON organizations USING gin(name gin_trgm_ops);",
                "CREATE INDEX IF NOT EXISTS idx_org_parent_org_id ON organizations(parent_org_id);",
                # Index for parent org
                # Employment indexes
                "CREATE INDEX IF NOT EXISTS idx_employment_person ON employment(person_id);",
                "CREATE INDEX IF NOT EXISTS idx_employment_org ON employment(org_id);",
                "CREATE INDEX IF NOT EXISTS idx_employment_dates ON employment(start_date, end_date);",
                "CREATE INDEX IF NOT EXISTS idx_employment_person_dates ON employment(person_id, start_date, end_date);",  # noqa: E501
                "CREATE INDEX IF NOT EXISTS idx_employment_org_dates ON employment(org_id, start_date, end_date);",
                "CREATE INDEX IF NOT EXISTS idx_employment_daterange ON employment USING gist(daterange(start_date, end_date, '[]'));",  # noqa: E501
                "CREATE INDEX IF NOT EXISTS idx_employment_colleague_lookup ON employment(org_id, start_date, end_date, person_id);",  # noqa: E501
            ]

            for index_sql in indexes:
                try:
                    cur.execute(index_sql)
                except Exception as e:
                    self.logger.warning(f"Index creation failed: {e}")

            self.logger.info("Database indexes created")

    def _create_materialized_views(self):
        """Create materialized views for performance"""
        with self.db.get_cursor() as cur:
            # Ensure tables it depends on exist before creating
            cur.execute("""
                CREATE MATERIALIZED VIEW IF NOT EXISTS colleague_pairs AS
                WITH overlapping_employments AS (
                    SELECT 
                        e1.person_id as person1_id,
                        e2.person_id as person2_id,
                        e1.org_id,
                        GREATEST(e1.start_date, e2.start_date) as overlap_start,
                        LEAST(e1.end_date, e2.end_date) as overlap_end,
                        LEAST(e1.end_date, e2.end_date) - GREATEST(e1.start_date, e2.start_date) + 1 as overlap_days
                    FROM employment e1
                    JOIN employment e2 ON e1.org_id = e2.org_id 
                    WHERE e1.person_id != e2.person_id
                    AND e1.start_date <= e2.end_date 
                    AND e2.start_date <= e1.end_date
                )
                SELECT 
                    p1.name as person1_name,
                    p2.name as person2_name,
                    o.name as organization,
                    oe.overlap_start,
                    oe.overlap_end,
                    oe.overlap_days
                FROM overlapping_employments oe
                JOIN people p1 ON oe.person1_id = p1.id
                JOIN people p2 ON oe.person2_id = p2.id
                JOIN organizations o ON oe.org_id = o.id
                WHERE oe.overlap_days > 0;
            """)

            # Create indexes on materialized view
            materialized_view_indexes = [
                "CREATE INDEX IF NOT EXISTS idx_colleague_pairs_person1 ON colleague_pairs(person1_name);",
                "CREATE INDEX IF NOT EXISTS idx_colleague_pairs_person2 ON colleague_pairs(person2_name);",
                "CREATE INDEX IF NOT EXISTS idx_colleague_pairs_org ON colleague_pairs(organization);",
            ]

            for index_sql in materialized_view_indexes:
                try:
                    cur.execute(index_sql)
                except Exception as e:
                    self.logger.warning(
                        f"Materialized view index creation failed: {e}"
                    )

            self.logger.info("Materialized views created")

    def _create_functions(self):
        """Create PostgreSQL functions"""
        with self.db.get_cursor() as cur:
            # Function to refresh materialized views
            cur.execute("""
                CREATE OR REPLACE FUNCTION refresh_colleague_pairs()
                RETURNS void AS $$
                BEGIN
                    REFRESH MATERIALIZED VIEW colleague_pairs;
                END;
                $$ LANGUAGE plpgsql;
            """)

            # Function to find colleagues at a specific date
            cur.execute("""
                CREATE OR REPLACE FUNCTION find_colleagues_at_date(
                    p_person_name VARCHAR(500),
                    p_target_date DATE
                )
                RETURNS TABLE(
                    colleague_name VARCHAR(500),
                    organization VARCHAR(1000),
                    colleague_rank VARCHAR(500),
                    start_date DATE,
                    end_date DATE,
                    overlap_days INTEGER
                ) AS $$
                BEGIN
                    RETURN QUERY
                    WITH person_orgs AS (
                        SELECT DISTINCT e.org_id, o.name as org_name
                        FROM employment e
                        JOIN people p ON e.person_id = p.id
                        JOIN organizations o ON e.org_id = o.id
                        WHERE p.name = p_person_name
                        AND p_target_date BETWEEN e.start_date AND e.end_date
                    )
                    SELECT DISTINCT 
                        p2.name::VARCHAR(255) as colleague_name,
                        po.org_name::VARCHAR(1000) as organization,
                        e2.rank::VARCHAR(500) as colleague_rank,
                        e2.start_date,
                        e2.end_date,
                        (LEAST(e2.end_date, p_target_date) - GREATEST(e2.start_date, p_target_date) + 1)::INTEGER as overlap_days
                    FROM employment e2
                    JOIN people p2 ON e2.person_id = p2.id
                    JOIN person_orgs po ON e2.org_id = po.org_id
                    WHERE p2.name != p_person_name
                    AND p_target_date BETWEEN e2.start_date AND e2.end_date
                    ORDER BY colleague_name;
                END;
                $$ LANGUAGE plpgsql;
            """)  # noqa: E501

            # Function to find all colleagues who have ever worked with a person
            cur.execute("""
                CREATE OR REPLACE FUNCTION find_all_colleagues(
                    p_person_name VARCHAR(500)
                )
                RETURNS TABLE(
                    colleague_name VARCHAR(500),
                    organization VARCHAR(1000),
                    colleague_rank VARCHAR(500),
                    colleague_start_date DATE,
                    colleague_end_date DATE,
                    person_start_date DATE,
                    person_end_date DATE,
                    overlap_start_date DATE,
                    overlap_end_date DATE,
                    overlap_days INTEGER
                ) AS $$
                BEGIN
                    RETURN QUERY
                    WITH person_employments AS (
                        SELECT e.org_id, e.start_date, e.end_date, o.name as org_name
                        FROM employment e
                        JOIN people p ON e.person_id = p.id
                        JOIN organizations o ON e.org_id = o.id
                        WHERE p.name = p_person_name
                    ),
                    colleague_overlaps AS (
                        SELECT DISTINCT 
                            p2.name as colleague_name,
                            pe.org_name as organization,
                            e2.rank as colleague_rank,
                            e2.start_date as colleague_start_date,
                            e2.end_date as colleague_end_date,
                            pe.start_date as person_start_date,
                            pe.end_date as person_end_date,
                            GREATEST(e2.start_date, pe.start_date) as overlap_start,
                            LEAST(e2.end_date, pe.end_date) as overlap_end
                        FROM employment e2
                        JOIN people p2 ON e2.person_id = p2.id
                        JOIN person_employments pe ON e2.org_id = pe.org_id
                        WHERE p2.name != p_person_name
                        AND e2.start_date <= pe.end_date
                        AND e2.end_date >= pe.start_date
                    )
                    SELECT 
                        co.colleague_name::VARCHAR(500),
                        co.organization::VARCHAR(1000),
                        co.colleague_rank::VARCHAR(500),
                        co.colleague_start_date,
                        co.colleague_end_date,
                        co.person_start_date,
                        co.person_end_date,
                        co.overlap_start as overlap_start_date,
                        co.overlap_end as overlap_end_date,
                        (co.overlap_end - co.overlap_start + 1)::INTEGER as overlap_days
                    FROM colleague_overlaps co
                    WHERE co.overlap_start <= co.overlap_end
                    ORDER BY co.colleague_name, co.organization, co.overlap_start;
                END;
                $$ LANGUAGE plpgsql;
            """)
            # self.db.conn.commit() # Commit is handled by the transaction context manager
            cur.execute("""
                CREATE OR REPLACE FUNCTION find_organizations_by_depth(
                    p_depth INTEGER
                )
                RETURNS TABLE(
                    id INTEGER,
                    name VARCHAR(1000),
                    department VARCHAR(500),
                    url VARCHAR(1000),
                    parent_org_id INTEGER,
                    metadata JSONB
                ) AS $$
                BEGIN
                    RETURN QUERY
                    SELECT
                        o.id,
                        o.name,
                        o.department,
                        o.url,
                        o.parent_org_id,
                        o.metadata
                    FROM
                        organizations o
                    WHERE
                        -- Check if the 'parts' key exists and is an array
                        o.metadata ? 'parts' AND
                        jsonb_typeof(o.metadata->'parts') = 'array' AND
                        -- This is the key condition: filter by array length
                        jsonb_array_length(o.metadata->'parts') = p_depth
                    ORDER BY
                        o.name;
                END;
                $$ LANGUAGE plpgsql;
            """)
            cur.execute("""
                CREATE OR REPLACE FUNCTION get_org_descendants_diff(
                p_parent_org_id INT,
                p_start_date TEXT,
                p_end_date TEXT
            )
            -- Defines the columns that this function will return in a table format
            RETURNS TABLE(
                org_id INT,
                name TEXT,
                status TEXT,
                details JSONB -- Returning the full end-state metadata can be useful
            )
            LANGUAGE sql AS $$

            -- This CTE finds all descendants of the parent, regardless of date.
            -- It's the base population we'll filter from.
            WITH RECURSIVE org_hierarchy AS (
                SELECT * FROM organizations WHERE id = p_parent_org_id
                UNION ALL
                SELECT o.* FROM organizations o
                JOIN org_hierarchy h ON o.parent_org_id = h.id
            ),

            -- This CTE filters the hierarchy to find orgs active on the START date.
            start_state AS (
                SELECT id, name, metadata FROM org_hierarchy
                WHERE
                    id != p_parent_org_id -- Exclude the parent itself
                    AND p_start_date::date >= COALESCE((metadata->>'first_observed')::date, '1900-01-01'::date)
                    AND p_start_date::date <= COALESCE((metadata->>'last_observed')::date, '9999-12-31'::date)
            ),

            -- This CTE filters the hierarchy to find orgs active on the END date.
            end_state AS (
                SELECT id, name, metadata FROM org_hierarchy
                WHERE
                    id != p_parent_org_id -- Exclude the parent itself
                    AND p_end_date::date >= COALESCE((metadata->>'first_observed')::date, '1900-01-01'::date)
                    AND p_end_date::date <= COALESCE((metadata->>'last_observed')::date, '9999-12-31'::date)
            )

            -- The final SELECT statement compares the two states.
            -- A FULL OUTER JOIN is perfect for finding differences between two sets.
            SELECT
                -- Use COALESCE to get the ID from whichever set has it.
                COALESCE(s.id, e.id) AS org_id,
                -- Prefer the name from the end_state, as it's more current.
                COALESCE(e.name, s.name) AS name,
                -- The CASE statement determines the status based on which set the org is in.
                CASE
                    WHEN s.id IS NULL THEN 'added'
                    WHEN e.id IS NULL THEN 'removed'
                    ELSE 'unchanged'
                END::TEXT AS status,
                -- Return the metadata from the end_state for added/unchanged orgs.
                e.metadata AS details
            FROM start_state s
            FULL OUTER JOIN end_state e ON s.id = e.id;

            $$;
            """)

            self.logger.info("Database functions created")

    def refresh_materialized_views(self):
        """Refresh all materialized views"""
        with self.db.get_cursor() as cur:
            cur.execute("SELECT refresh_colleague_pairs();")
        # self.db.conn.commit() # Commit is handled by the transaction context manager
        self.logger.info("Materialized views refreshed")
