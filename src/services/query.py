from typing import List, Dict, Union, Optional, Tuple, Any
from src.database.postgres.connection import AsyncDatabaseConnection
from src.repositories.employment import EmploymentRepository
from src.repositories.organisations import OrganisationsRepository
from datetime import datetime
from loguru import logger
from thefuzz import fuzz  # Added for fuzzywuzzy
from src.common.utils import recursively_make_hashable

# Default similarity threshold for fuzzy matching
DEFAULT_MIN_SIMILARITY_THRESHOLD = 0.5
# Default maximum number of similar names to consider in fuzzy search
DEFAULT_MAX_SIMILAR_NAMES = 3
# Default threshold for the secondary "highly related" filter
DEFAULT_SECONDARY_PAIRWISE_THRESHOLD = 0.80  # For fuzz.WRatio

# Default minimum number of strong pairwise links for a name to be kept
DEFAULT_MIN_STRONG_PAIRWISE_LINKS = (
    1  # Must be similar to at least 1 other in the set
)


class QueryService:
    def __init__(
        self,
        db_connection: AsyncDatabaseConnection,
        employment_repo: EmploymentRepository,
        org_repo: OrganisationsRepository,
    ):
        self.db = db_connection
        self.logger = logger
        self.employment_repo = employment_repo
        self.org_repo = org_repo

    async def _get_similar_person_names(
        self,
        name_query: str,
        pg_similarity_threshold: float,
        fw_primary_similarity_threshold: float,
        limit_results: int,
        enable_pairwise_filter: bool = True,
        fw_pairwise_similarity_threshold: float = DEFAULT_SECONDARY_PAIRWISE_THRESHOLD,
        min_strong_pairwise_links: int = DEFAULT_MIN_STRONG_PAIRWISE_LINKS,
    ) -> List[str]:
        """
        Finds a list of person names similar to the query.
        1. Uses PostgreSQL trigram similarity (or ILIKE fallback) for initial candidates.
        2. Refines with a primary fuzzywuzzy filter (e.g., token_set_ratio) against the query.
        3. Optionally, applies a secondary fuzzywuzzy filter to ensure candidates are
           highly related to the best match from step 2.
        """
        pg_candidates_with_pg_score: List[Tuple[str, Optional[float]]] = []
        pg_search_method_used = "None"
        # Fetch more from PG to give fuzzywuzzy a better pool
        sql_query_limit = max(
            limit_results * 5, 20
        )  # Increased for better candidate pool

        try:
            async with self.db.acquire() as conn:
                results = await conn.fetch(
                    """
                    SELECT clean_name, similarity(clean_name, $1) AS sim_score
                    FROM people
                    WHERE clean_name % $1 AND similarity(clean_name, $1) >= $2
                    ORDER BY sim_score DESC
                    LIMIT $3;
                    """,
                    name_query,
                    pg_similarity_threshold,
                    sql_query_limit,
                )
                if results:
                    pg_candidates_with_pg_score = [
                        (r["clean_name"], r["sim_score"]) for r in results
                    ]
                    pg_search_method_used = "trigram"
                else:
                    # Fallback to ILIKE if trigram returns nothing
                    self.logger.info(
                        f"No trigram results for '{name_query}'. Falling back to ILIKE."
                    )
                    results = await conn.fetch(
                        "SELECT clean_name FROM people WHERE clean_name ILIKE $1 LIMIT $2",
                        f"%{name_query}%",
                        sql_query_limit,
                    )
                    pg_candidates_with_pg_score = [
                        (r["clean_name"], None) for r in results
                    ]
                    pg_search_method_used = "ILIKE"
        except Exception as e:
            if hasattr(e, "pgcode") and e.pgcode == "42883":
                self.logger.warning(
                    f"Trigram functions failed for '{name_query}'. Falling back to ILIKE. Error: {e}"
                )
                try:
                    async with self.db.acquire() as conn:
                        results = await conn.fetch(
                            "SELECT clean_name FROM people WHERE clean_name ILIKE $1 LIMIT $2",
                            f"%{name_query}%",
                            sql_query_limit,
                        )
                        pg_candidates_with_pg_score = [
                            (r["clean_name"], None) for r in results
                        ]
                        pg_search_method_used = "ILIKE"
                except Exception as e_fallback:
                    self.logger.error(
                        f"Fallback ILIKE search failed for '{name_query}': {e_fallback}"
                    )
                    return []
            else:
                self.logger.error(
                    f"Database error during trigram search for '{name_query}': {e}"
                )
                return []

        if not pg_candidates_with_pg_score:
            self.logger.info(
                f"No initial candidates found from PostgreSQL for '{name_query}'."
            )
            return []

        # Primary FuzzyWuzzy refinement (using token_set_ratio for order insensitivity)
        fw_primary_threshold_int = int(
            fw_primary_similarity_threshold * 100
        )
        primary_refined_candidates: List[Tuple[str, int]] = []
        query_lower = name_query.lower()

        self.logger.info(
            f"Applying primary FuzzyWuzzy refinement (token_set_ratio >= {fw_primary_threshold_int}%) "
            f"to {len(pg_candidates_with_pg_score)} PG candidates for '{name_query}'."
        )
        for cand_name, pg_score in pg_candidates_with_pg_score:
            fw_score = fuzz.token_set_ratio(query_lower, cand_name.lower())
            pg_score_display = (
                f"{pg_score:.4f}" if pg_score is not None else "N/A (ILIKE)"
            )
            if fw_score >= fw_primary_threshold_int:
                primary_refined_candidates.append((cand_name, fw_score))
                self.logger.debug(
                    f"  Primary FW: Candidate '{cand_name}' (PG Sim: {pg_score_display}) "
                    f"-> token_set_ratio: {fw_score}%. Kept."
                )
            else:
                self.logger.debug(
                    f"  Primary FW: Candidate '{cand_name}' (PG Sim: {pg_score_display}) "
                    f"-> token_set_ratio: {fw_score}%. Discarded (below {fw_primary_threshold_int}%)."
                )

        if not primary_refined_candidates:
            self.logger.info(
                f"No candidates for '{name_query}' passed primary FuzzyWuzzy filter "
                f"(threshold {fw_primary_threshold_int}%)."
            )
            return []

        primary_refined_candidates.sort(key=lambda x: x[1], reverse=True)

        # --- Secondary Pairwise FuzzyWuzzy Filtering Layer ---
        if (
            not enable_pairwise_filter
            or len(primary_refined_candidates) <= 1
        ):
            if not enable_pairwise_filter:
                self.logger.info(
                    "Pairwise similarity filter skipped by configuration."
                )
            else:
                self.logger.info(
                    "Pairwise similarity filter skipped: <=1 candidate after primary filter."
                )
            final_names_after_filtering = [
                name for name, score in primary_refined_candidates
            ]
        # If pairwise filtering is enabled and we have enough candidates
        elif len(primary_refined_candidates) <= min_strong_pairwise_links:
            self.logger.warning(
                f"Pairwise similarity filter skipped: only {len(primary_refined_candidates)} candidates "
                f"after primary filter, which is less than the minimum required ({min_strong_pairwise_links})."
            )
            final_names_after_filtering = [
                name for name, _ in primary_refined_candidates
            ]
        else:
            fw_pairwise_threshold_int = int(
                fw_pairwise_similarity_threshold * 100
            )
            candidates_with_links: List[
                Tuple[str, int, int]
            ] = []  # (name, primary_score, num_strong_links)

            num_primary_candidates = len(primary_refined_candidates)
            self.logger.info(
                f"Applying pairwise similarity filter to {num_primary_candidates} candidates for '{name_query}'. "
                f"Pairwise WRatio threshold: >={fw_pairwise_threshold_int}%, "
                f"Min strong links required: {min_strong_pairwise_links}."
            )
            if (
                num_primary_candidates > 25
            ):  # Heuristic warning for performance
                self.logger.warning(
                    f"Pairwise comparison on a large set ({num_primary_candidates} candidates). This might be slow."
                )

            for i in range(num_primary_candidates):
                cand_name_i, primary_score_i = primary_refined_candidates[i]
                num_strong_links = 0
                for j in range(num_primary_candidates):
                    if i == j:
                        continue
                    cand_name_j, _ = primary_refined_candidates[j]
                    pairwise_score = fuzz.token_set_ratio(
                        cand_name_i.lower(), cand_name_j.lower()
                    )
                    if pairwise_score >= fw_pairwise_threshold_int:
                        num_strong_links += 1

                if num_strong_links >= min_strong_pairwise_links:
                    candidates_with_links.append(
                        (cand_name_i, primary_score_i, num_strong_links)
                    )
                    self.logger.debug(
                        f"  Pairwise FW: '{cand_name_i}' (Primary score: {primary_score_i}%) "
                        f"has {num_strong_links} strong pairwise links. Kept for now."
                    )
                else:
                    self.logger.debug(
                        f"  Pairwise FW: '{cand_name_i}' (Primary score: {primary_score_i}%) "
                        f"has {num_strong_links} strong links (less than {min_strong_pairwise_links}). Discarded."
                    )

            if not candidates_with_links:
                self.logger.info(
                    f"No candidates for '{name_query}' passed pairwise filter."
                )
                return []

            # Sort by number of strong links (desc), then by primary score (desc)
            candidates_with_links.sort(
                key=lambda x: (x[2], x[1]), reverse=True
            )
            final_names_after_filtering = [
                name for name, _, _ in candidates_with_links
            ]

        # Apply the final limit_results
        limited_final_names = final_names_after_filtering[:limit_results]

        if limited_final_names:
            self.logger.info(
                f"Final {len(limited_final_names)} similar names for '{name_query}' "
                f"after all filters and limit ({limit_results}): {limited_final_names}"
            )
        else:
            self.logger.info(
                f"No similar names for '{name_query}' remain after all filtering and limit."
            )
        return limited_final_names

    def _deduplicate_list_of_dicts(
        self, list_of_dicts: List[Dict]
    ) -> List[Dict]:
        """Deduplicates a list of dictionaries."""
        seen: set[Tuple[Tuple[Any, Any], ...]] = set()
        deduplicated_list: List[Dict] = []

        for d_item in list_of_dicts:
            try:
                # Use the utility function here
                frozen_representation = recursively_make_hashable(d_item)
            except TypeError:
                # print(f"Error creating hashable representation for {d_item}: {e}")
                raise

            if frozen_representation not in seen:
                seen.add(frozen_representation)
                deduplicated_list.append(d_item)
        return deduplicated_list

    async def find_colleagues_at_date(
        self,
        person_name: str,
        target_date: Optional[str] = None,
        is_fuzzy: bool = False,
        min_similarity_threshold: float = DEFAULT_MIN_SIMILARITY_THRESHOLD,
        fw_primary_similarity_threshold: float = DEFAULT_MIN_SIMILARITY_THRESHOLD,
        max_similar_names: int = DEFAULT_MAX_SIMILAR_NAMES,
        # Parameters for pairwise secondary filter
        enable_pairwise_deep_check: Optional[
            bool
        ] = None,  # Renamed for clarity
        fw_pairwise_check_threshold: float = DEFAULT_SECONDARY_PAIRWISE_THRESHOLD,
        min_links_for_pairwise_check: int = DEFAULT_MIN_STRONG_PAIRWISE_LINKS,
    ) -> List[Dict]:
        """Find colleagues, optionally using fuzzy search for multiple similar names."""
        names_to_query: List[str] = [person_name]
        if is_fuzzy:
            should_enable_pairwise = (
                enable_pairwise_deep_check
                if enable_pairwise_deep_check is not None
                else True
            )
            similar_names = await self._get_similar_person_names(
                name_query=person_name,
                pg_similarity_threshold=min_similarity_threshold,
                fw_primary_similarity_threshold=fw_primary_similarity_threshold,
                limit_results=max_similar_names,
                enable_pairwise_filter=should_enable_pairwise,
                fw_pairwise_similarity_threshold=fw_pairwise_check_threshold,
                min_strong_pairwise_links=min_links_for_pairwise_check,
            )
            if not similar_names:
                return []
            names_to_query = similar_names
            self.logger.info(
                f"Using names {names_to_query} (found via fuzzy search for '{person_name}') "
                "for find_colleagues_at_date."
            )

        if target_date is None:
            target_date = datetime.now().strftime("%Y-%m-%d")

        all_colleagues: List[Dict] = []
        try:
            async with self.db.acquire() as conn:
                # Using ANY($1) to pass a list of names
                results = await conn.fetch(
                    """
                    SELECT DISTINCT p2.name as colleague_name, o.name as org_name, e2.rank as colleague_rank
                    FROM employment e1
                    JOIN people p1 ON e1.person_id = p1.id
                    JOIN employment e2 ON e1.org_id = e2.org_id AND e1.id != e2.id
                    JOIN people p2 ON e2.person_id = p2.id
                    JOIN organizations o ON e1.org_id = o.id
                    WHERE p1.name = ANY($1)
                    AND $2::date BETWEEN e1.start_date AND e1.end_date
                    AND $2::date BETWEEN e2.start_date AND e2.end_date;
                    """,
                    names_to_query,
                    target_date,
                )
                all_colleagues = [dict(row) for row in results]
        except Exception as e:
            self.logger.error(
                f"Error finding colleagues for names derived from '{person_name}': {e}"
            )
            return []

        return self._deduplicate_list_of_dicts(all_colleagues)

    async def find_all_colleagues(
        self,
        person_name: str,
        is_fuzzy: bool = False,
        min_similarity_threshold: float = DEFAULT_MIN_SIMILARITY_THRESHOLD,
        max_similar_names: int = DEFAULT_MAX_SIMILAR_NAMES,
    ) -> List[Dict]:
        """Find all colleagues, optionally using fuzzy search for multiple similar names."""
        names_to_query: List[str] = [person_name]
        if is_fuzzy:
            similar_names = await self._get_similar_person_names(
                person_name, min_similarity_threshold, max_similar_names
            )
            if not similar_names:
                return []
            names_to_query = similar_names
            self.logger.info(
                f"Using names {names_to_query} (found via fuzzy search for '{person_name}') "
                "for find_all_colleagues."
            )

        all_colleagues: List[Dict] = []
        try:
            async with self.db.acquire() as conn:
                results = await conn.fetch(
                    """
                    SELECT DISTINCT p2.name as colleague_name, o.name as org_name, e2.rank as colleague_rank
                    FROM employment e1
                    JOIN people p1 ON e1.person_id = p1.id
                    JOIN employment e2 ON e1.org_id = e2.org_id AND e1.id != e2.id
                    JOIN people p2 ON e2.person_id = p2.id
                    JOIN organizations o ON e1.org_id = o.id
                    WHERE p1.name = ANY($1);
                    """,
                    names_to_query,
                )
                all_colleagues = [dict(row) for row in results]
        except Exception as e:
            self.logger.error(
                f"Error finding all colleagues for names derived from '{person_name}': {e}"
            )
            return []

        return self._deduplicate_list_of_dicts(all_colleagues)

    async def get_career_progression_by_name(
        self,
        person_name: str,
        is_fuzzy: bool = False,
        min_similarity_threshold: float = DEFAULT_MIN_SIMILARITY_THRESHOLD,
        fw_primary_similarity_threshold: float = DEFAULT_MIN_SIMILARITY_THRESHOLD,
        max_similar_names: int = DEFAULT_MAX_SIMILAR_NAMES,
        # Parameters for pairwise secondary filter
        enable_pairwise_deep_check: Optional[
            bool
        ] = None,  # Renamed for clarity
        fw_pairwise_check_threshold: float = DEFAULT_SECONDARY_PAIRWISE_THRESHOLD,
        min_links_for_pairwise_check: int = DEFAULT_MIN_STRONG_PAIRWISE_LINKS,
        get_parent_orgs: bool = True,
        cluster_by_rank_and_entity: bool = True,
    ) -> List[Dict]:
        """Get career progression, optionally using fuzzy search for multiple similar names."""
        names_to_query: List[str] = [person_name]
        if is_fuzzy:
            should_enable_pairwise = (
                enable_pairwise_deep_check
                if enable_pairwise_deep_check is not None
                else True
            )
            similar_names = await self._get_similar_person_names(
                name_query=person_name,
                pg_similarity_threshold=min_similarity_threshold,
                fw_primary_similarity_threshold=fw_primary_similarity_threshold,
                limit_results=max_similar_names,
                enable_pairwise_filter=should_enable_pairwise,
                fw_pairwise_similarity_threshold=fw_pairwise_check_threshold,
                min_strong_pairwise_links=min_links_for_pairwise_check,
            )
            if not similar_names:
                return []
            names_to_query = similar_names
            self.logger.info(
                f"Using names {names_to_query} (found via fuzzy search for '{person_name}') "
                "for get_career_progression."
            )

        all_progressions: List[Dict] = []
        try:
            async with self.db.acquire() as conn:
                results = await conn.fetch(
                    """
                    SELECT
                        p.name as person_name,
                        p.id as person_id,
                        e.rank,
                        o.name as entity_name,
                        o.id as org_id,
                        e.start_date,
                        e.end_date
                    FROM employment e
                    JOIN people p ON e.person_id = p.id
                    JOIN organizations o ON e.org_id = o.id
                    WHERE p.name = ANY($1)
                    ORDER BY e.start_date;
                    """,
                    names_to_query,
                )
                all_progressions = [dict(row) for row in results]
        except Exception as e:
            self.logger.error(
                f"Error getting career progression for names derived from '{person_name}': {e}"
            )
            return []

        if all_progressions and get_parent_orgs:
            for profile in all_progressions:
                try:
                    profile[
                        "linked_organizations"
                    ] = await self.org_repo.get_all_ancestors(
                        profile["org_id"]
                    )
                except Exception as e:
                    self.logger.error(
                        f"Error getting linked organizations for profile {profile['id']}: {e}"
                    )

        if cluster_by_rank_and_entity:
            self.logger.info(
                f"Clustering career progression by rank and entity name. Initial count: {len(all_progressions)}"
            )
            all_progressions = self._deduplicate_employment_profiles(
                all_progressions,
            )
            self.logger.info(
                f"After clustering, count: {len(all_progressions)}"
            )

        return self._deduplicate_list_of_dicts(all_progressions)

    def _deduplicate_employment_profiles(
        self,
        employment_profiles: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Deduplicates employment profiles based on rank and entity name. If the rank and entity name is the same, ensure that the start and end dates are extended to cover the full period.
        This is useful for cases where a person has multiple employment records with the same rank and entity
        """
        if not employment_profiles:
            return []
        seen: set[Tuple[str, str]] = set()
        deduplicated_profiles: List[Dict[str, Any]] = []
        for profile in employment_profiles:
            key = (profile["rank"], profile["entity_name"])
            if key not in seen:
                seen.add(key)
                deduplicated_profiles.append(profile)
            else:
                # If we have seen this rank and entity before, extend the dates
                for existing_profile in deduplicated_profiles:
                    if (
                        existing_profile["rank"] == profile["rank"]
                        and existing_profile["entity_name"]
                        == profile["entity_name"]
                    ):
                        existing_profile["start_date"] = min(
                            existing_profile["start_date"],
                            profile["start_date"],
                        )
                        existing_profile["end_date"] = max(
                            existing_profile["end_date"],
                            profile["end_date"],
                        )
                        existing_profile["tenure_days"] = (
                            existing_profile["end_date"]
                            - existing_profile["start_date"]
                        ).days
        return deduplicated_profiles

    async def get_career_progression_by_person_id(
        self,
        person_id: int,
        get_parent_orgs: bool = True,
    ) -> List[Dict]:
        """Get career progression by person ID."""
        all_progressions: List[Dict] = []
        try:
            async with self.db.acquire() as conn:
                results = await conn.fetch(
                    """
                    SELECT
                        p.name as person_name,
                        p.id as person_id,
                        e.rank,
                        o.name as entity_name,
                        o.id as org_id,
                        e.start_date,
                        e.end_date
                    FROM employment e
                    JOIN people p ON e.person_id = p.id
                    JOIN organizations o ON e.org_id = o.id
                    WHERE p.id = $1
                    ORDER BY e.start_date;
                    """,
                    person_id,
                )
                all_progressions = [dict(row) for row in results]
        except Exception as e:
            self.logger.error(
                f"Error getting career progression for person ID {person_id}: {e}"
            )
            return []

        if all_progressions and get_parent_orgs:
            for profile in all_progressions:
                try:
                    profile[
                        "linked_organizations"
                    ] = await self.org_repo.get_all_ancestors(
                        profile["org_id"]
                    )
                except Exception as e:
                    self.logger.error(
                        f"Error getting linked organizations for profile {profile['id']}: {e}"
                    )

        return self._deduplicate_list_of_dicts(all_progressions)

    async def get_network_snapshot(self, target_date: str) -> List[Dict]:
        """
        Gets the network state at a specific date, including the unique IDs
        for people and organizations.
        """
        try:
            async with self.db.acquire() as conn:
                results = await conn.fetch(
                    """
                    SELECT
                        p.id as person_id,
                        p.name as person_name,
                        o.id as org_id,
                        o.name as org_name,
                        e.rank,
                        e.start_date,
                        e.end_date
                    FROM employment e
                    JOIN people p ON e.person_id = p.id
                    JOIN organizations o ON e.org_id = o.id
                    WHERE $1::date BETWEEN e.start_date AND e.end_date;
                    """,
                    target_date,
                )
                return [dict(row) for row in results]
        except Exception as e:
            self.logger.error(f"Error getting network snapshot: {e}")
            return []

    async def find_people_by_temporal_overlap(
        self,
        person_id: int,
        name_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Finds people connected to a given person via overlapping employment.
        """
        self.logger.info(
            f"Finding temporal connections for person_id: {person_id}"
        )
        return await self.employment_repo.find_people_with_overlapping_employment(
            person_id, name_filter, limit
        )

    async def find_employment_by_person_id(
        self,
        person_id: int,
        limit: int = 50,
        get_recent_employment: bool = False,
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Finds employment connected to a given person ID.
        """
        res = await self.employment_repo.find_by_person_id(person_id, limit)
        if get_recent_employment and res:
            # Sort by start_date descending to get the most recent employment first
            res.sort(key=lambda x: x["start_date"], reverse=True)[0]
        return res

    async def get_all_employment_data(self) -> List[Dict]:
        """
        Gets the entire network history, including unique IDs for people
        and organizations, across all time.
        """
        self.logger.info("Fetching all historical employment data.")
        try:
            async with self.db.acquire() as conn:
                results = await conn.fetch(
                    """
                    SELECT
                        p.id as person_id,
                        p.name as person_name,
                        o.id as org_id,
                        o.name as org_name,
                        e.rank,
                        e.start_date,
                        e.end_date
                    FROM employment e
                    JOIN people p ON e.person_id = p.id
                    JOIN organizations o ON e.org_id = o.id;
                    """
                )
                return [dict(row) for row in results]
        except Exception as e:
            self.logger.error(f"Error getting all employment data: {e}")
            return []
