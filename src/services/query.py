from typing import List, Dict, Union, Optional, Tuple, Any
from src.database.postgres.connection import DatabaseConnection
from datetime import datetime
import logging
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
    def __init__(self, db_connection: DatabaseConnection):
        self.db = db_connection
        self.logger = logging.getLogger(__name__)

    def _get_similar_person_names(
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
            with self.db.get_cursor() as cur:
                cur.execute(
                    """
                    SELECT clean_name, similarity(clean_name, %s) AS sim_score
                    FROM people
                    WHERE clean_name %% %s AND similarity(clean_name, %s) >= %s
                    ORDER BY sim_score DESC
                    LIMIT %s;
                    """,
                    (
                        name_query,
                        name_query,
                        name_query,
                        pg_similarity_threshold,
                        sql_query_limit,
                    ),
                )
                results = cur.fetchall()
                if results:
                    for row in results:
                        pg_candidates_with_pg_score.append(
                            (row["clean_name"], row["sim_score"])
                        )
                    pg_search_method_used = "PostgreSQL Trigram"
                    self.logger.info(
                        f"{pg_search_method_used} search for '{name_query}' found "
                        f"{len(pg_candidates_with_pg_score)} initial candidates "
                        f"(PG threshold >={pg_similarity_threshold}, SQL limit {sql_query_limit})."
                    )
                else:
                    self.logger.info(
                        f"No trigram matches found for '{name_query}' above threshold "
                        f"{pg_similarity_threshold} using '%%' operator."
                    )
        except Exception as e:
            if hasattr(e, "pgcode") and e.pgcode == "42883":
                self.logger.warning(
                    f"Trigram functions failed for '{name_query}'. Falling back to ILIKE. Error: {e}"
                )
                try:
                    with self.db.get_cursor() as cur_fallback:
                        cur_fallback.execute(
                            """
                            SELECT clean_name
                            FROM people
                            WHERE clean_name ILIKE %s
                            ORDER BY length(clean_name) ASC, clean_name ASC
                            LIMIT %s;
                            """,
                            (f"%{name_query}%", sql_query_limit),
                        )
                        results_fallback = cur_fallback.fetchall()
                        if results_fallback:
                            for row_fallback in results_fallback:
                                pg_candidates_with_pg_score.append(
                                    (row_fallback["clean_name"], None)
                                )
                            pg_search_method_used = (
                                "PostgreSQL ILIKE (fallback)"
                            )
                            self.logger.info(
                                f"{pg_search_method_used} search for '{name_query}' found "
                                f"{len(results_fallback)} initial candidates (SQL limit {sql_query_limit})."
                            )
                        else:
                            self.logger.warning(
                                f"Fallback ILIKE search for '{name_query}' found no results."
                            )
                except Exception as e_fallback:
                    self.logger.error(
                        f"Error during fallback ILIKE search for '{name_query}': {e_fallback}"
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

    def find_colleagues_at_date(
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
            similar_names = self._get_similar_person_names(
                name_query=person_name,
                pg_similarity_threshold=min_similarity_threshold,
                fw_primary_similarity_threshold=fw_primary_similarity_threshold,
                limit_results=max_similar_names,
                enable_pairwise_filter=should_enable_pairwise,
                fw_pairwise_similarity_threshold=fw_pairwise_check_threshold,
                min_strong_pairwise_links=min_links_for_pairwise_check,
            )
            if not similar_names:
                self.logger.info(
                    f"No suitable fuzzy matches for '{person_name}' for find_colleagues_at_date. "
                    "Returning empty list."
                )
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
            with self.db.get_cursor() as cur:
                for name_to_use in names_to_query:
                    cur.execute(
                        "SELECT * FROM find_colleagues_at_date(%s, %s)",
                        (name_to_use, target_date),
                    )
                    results = [dict(row) for row in cur.fetchall()]
                    all_colleagues.extend(results)
                    if results:
                        self.logger.debug(
                            f"Found {len(results)} colleagues for '{name_to_use}' at {target_date}."
                        )
        except Exception as e:
            self.logger.error(
                f"Error finding colleagues for names derived from '{person_name}': {e}"
            )
            return []

        return self._deduplicate_list_of_dicts(all_colleagues)

    def find_all_colleagues(
        self,
        person_name: str,
        is_fuzzy: bool = False,
        min_similarity_threshold: float = DEFAULT_MIN_SIMILARITY_THRESHOLD,
        max_similar_names: int = DEFAULT_MAX_SIMILAR_NAMES,
    ) -> List[Dict]:
        """Find all colleagues, optionally using fuzzy search for multiple similar names."""
        names_to_query: List[str] = [person_name]
        if is_fuzzy:
            similar_names = self._get_similar_person_names(
                person_name, min_similarity_threshold, max_similar_names
            )
            if not similar_names:
                self.logger.info(
                    f"No suitable fuzzy matches for '{person_name}' for find_all_colleagues. "
                    "Returning empty list."
                )
                return []
            names_to_query = similar_names
            self.logger.info(
                f"Using names {names_to_query} (found via fuzzy search for '{person_name}') "
                "for find_all_colleagues."
            )

        all_colleagues: List[Dict] = []
        try:
            with self.db.get_cursor() as cur:
                for name_to_use in names_to_query:
                    cur.execute(
                        "SELECT * FROM find_all_colleagues(%s)",
                        (name_to_use,),
                    )
                    results = [dict(row) for row in cur.fetchall()]
                    all_colleagues.extend(results)
                    if results:
                        self.logger.debug(
                            f"Found {len(results)} total colleagues for '{name_to_use}'."
                        )

        except Exception as e:
            self.logger.error(
                f"Error finding all colleagues for names derived from '{person_name}': {e}"
            )
            return []

        return self._deduplicate_list_of_dicts(all_colleagues)

    def get_career_progression(
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
    ) -> List[Dict]:
        """Get career progression, optionally using fuzzy search for multiple similar names."""
        names_to_query: List[str] = [person_name]
        if is_fuzzy:
            should_enable_pairwise = (
                enable_pairwise_deep_check
                if enable_pairwise_deep_check is not None
                else True
            )
            similar_names = self._get_similar_person_names(
                name_query=person_name,
                pg_similarity_threshold=min_similarity_threshold,
                fw_primary_similarity_threshold=fw_primary_similarity_threshold,
                limit_results=max_similar_names,
                enable_pairwise_filter=should_enable_pairwise,
                fw_pairwise_similarity_threshold=fw_pairwise_check_threshold,
                min_strong_pairwise_links=min_links_for_pairwise_check,
            )
            if not similar_names:
                self.logger.info(
                    f"No suitable fuzzy matches for '{person_name}' for get_career_progression. "
                    "Returning empty list."
                )
                return []
            names_to_query = similar_names
            self.logger.info(
                f"Using names {names_to_query} (found via fuzzy search for '{person_name}') "
                "for get_career_progression."
            )

        all_progressions: List[Dict] = []
        try:
            with self.db.get_cursor() as cur:
                for name_to_use in names_to_query:
                    cur.execute(
                        """
                        SELECT
                            p.name as person_actual_name,
                            o.name as entity_name,
                            o.department as department_name,
                            po.name as parent_organization_name, 
                            o.metadata as entity_metadata,
                            e.rank,
                            e.start_date,
                            e.end_date,
                            e.tenure_days,
                            ROW_NUMBER() OVER (PARTITION BY p.id ORDER BY e.start_date) as sequence_number
                        FROM employment e
                        JOIN people p ON e.person_id = p.id
                        JOIN organizations o ON e.org_id = o.id
                        LEFT JOIN organizations po ON o.parent_org_id = po.id 
                        WHERE p.name = %s
                        ORDER BY p.id, e.start_date
                        """,
                        (name_to_use,),
                    )
                    results = [dict(row) for row in cur.fetchall()]
                    all_progressions.extend(results)
                    if results:
                        self.logger.debug(
                            f"Found {len(results)} career progression entries for '{name_to_use}'."
                        )
        except Exception as e:
            self.logger.error(
                f"Error getting career progression for names derived from '{person_name}': {e}"
            )
            return []

        return self._deduplicate_list_of_dicts(all_progressions)

    def get_network_snapshot(self, target_date: str) -> List[Dict]:
        """Get network state at specific date (no changes for fuzzy search here)."""
        try:
            with self.db.get_cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        p.name as person_name,
                        o.name as org_name,
                        e.rank,
                        e.start_date,
                        e.end_date,
                        p.tel,
                        p.email
                    FROM employment e
                    JOIN people p ON e.person_id = p.id
                    JOIN organizations o ON e.org_id = o.id
                    WHERE %s BETWEEN e.start_date AND e.end_date
                    ORDER BY o.name, p.name
                """,
                    (target_date,),
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            self.logger.error(f"Error getting network snapshot: {e}")
            return []
