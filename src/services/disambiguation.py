from datetime import timedelta
from typing import List, Dict, Any, Optional

# Assuming your repositories are importable
# from src.repositories.people import PeopleRepository
from src.repositories.organisations import OrganisationsRepository


class RankParser:
    """
    Parses a raw job title string into a numerical seniority score.
    This component-based approach is more robust and comprehensive than
    a simple keyword dictionary.
    """

    def __init__(self):
        # These dictionaries are the core of the heuristic.
        # They should be tuned and expanded based on your specific data.

        # 1. Level Modifiers: Adjusts the base score.
        self.LEVEL_MODIFIERS = {
            "junior": -2,
            "jr": -2,
            "associate": -1,
            "assistant": -1,  # e.g., Assistant Manager
            "senior": 2,
            "sr": 2,
            "lead": 3,
            "principal": 4,
            "(covering)": 0,  # Often temporary, treat as neutral
        }

        # 2. Role Keywords: Provides the base score for a job family.
        self.ROLE_KEYWORDS = {
            "intern": 1,
            "officer": 5,
            "executive": 5,
            "specialist": 6,
            "analyst": 6,
            "engineer": 7,
            "consultant": 7,
            "scientist": 8,
            "counsel": 8,
            "manager": 10,
        }

        # 3. Management Tiers: High-value keywords for leadership roles.
        self.MANAGEMENT_TIERS = {
            "head": 15,
            "assistant director": 18,
            "director": 20,
            "deputy director": 19,
            "senior director": 22,
            "vice president": 25,
            "vp": 25,
            "chief": 30,  # e.g., Chief Financial Officer
        }

        self.PERMISSIBLE_OVERLAP_KEYWORDS = {
            "board member",
            "advisor",
            "adviser",
            "consultant",
            "non-executive",
            "fellow",
            "mentor",
        }

    def parse_rank(self, title: str) -> int:
        """
        Calculates a seniority score for a given job title.

        Returns:
            An integer score. Higher scores indicate higher seniority.
        """
        if not title:
            return 0

        # Normalize title for matching
        lower_title = " " + title.lower() + " "

        score = 0
        found_role_base = False

        # --- Step 1: Check for high-level management tiers first ---
        # These are often the most definitive part of a title.
        # We check for longer phrases first to avoid partial matches
        # (e.g., match "assistant director" before "director").
        for tier, value in sorted(
            self.MANAGEMENT_TIERS.items(),
            key=lambda x: len(x[0]),
            reverse=True,
        ):
            if " " + tier + " " in lower_title:
                score += value
                # Remove the matched part to avoid double counting
                lower_title = lower_title.replace(" " + tier + " ", " ")
                found_role_base = True
                break  # Assume only one management tier per title

        # --- Step 2: Find the core role keyword for a base score ---
        if not found_role_base:
            for role, value in self.ROLE_KEYWORDS.items():
                if " " + role + " " in lower_title:
                    score += value
                    lower_title = lower_title.replace(" " + role + " ", " ")
                    break  # Take the first one found

        # --- Step 3: Add score from level modifiers ---
        for modifier, value in self.LEVEL_MODIFIERS.items():
            if " " + modifier + " " in lower_title:
                score += value
                # Don't break here, a title could have multiple (though rare)

        return score

    def is_permissible_overlap(self, title: str) -> bool:
        """
        Checks if a job title contains keywords suggesting it's a role
        that can be held concurrently with another job.
        """
        if not title:
            return False
        lower_title = title.lower()
        for keyword in self.PERMISSIBLE_OVERLAP_KEYWORDS:
            if keyword in lower_title:
                return True
        return False


class DisambiguationService:
    """
    A service to disambiguate employment records by clustering them into
    distinct career paths for individuals with the same name.
    """

    # --- Heuristic Configuration ---
    RANK_HIERARCHY: Dict[str, int] = {
        "officer": 1,
        "manager": 2,
        "senior manager": 3,
        "assistant director": 4,
        "senior legal counsel": 4,
        "director": 5,
    }

    COHESION_SCORES: Dict[str, int] = {
        "SAME_PARENT_MINISTRY": 5,
        "LOGICAL_PROMOTION": 3,
        "LATERAL_MOVE": 1,
        "ILLOGICAL_DEMOTION": -10,
        "IMMEDIATE_SUCCESSION": 4,
        "QUICK_SUCCESSION": 2,
        "PERMISSIBLE_OVERLAP_PENALTY": -2,  # Penalize but don't forbid
    }

    MINIMUM_COHESION_THRESHOLD: int = 1

    def __init__(
        self, orgs_repo: OrganisationsRepository
    ):  # Use your actual Org Repo type
        """
        Initializes the service with necessary database repositories.

        Args:
            orgs_repo: An instance of OrganisationsRepository.
        """
        self.orgs_repo = orgs_repo
        self.rank_parser = RankParser()

    def _has_temporal_overlap(
        self, record1: Dict[str, Any], record2: Dict[str, Any]
    ) -> bool:
        """Simple helper to check for any date overlap."""
        return (
            record1["start_date"] <= record2["end_date"]
            and record1["end_date"] >= record2["start_date"]
        )

    def _is_hard_conflict(
        self, record1: Dict[str, Any], record2: Dict[str, Any]
    ) -> bool:
        """
        Determines if two roles represent a "Hard Conflict".
        This is true only if they overlap AND neither role is of a type
        that permits overlapping (e.g., both are full-time operational roles).
        """
        if not self._has_temporal_overlap(record1, record2):
            return False

        # Check the nature of each role using the RankParser
        is_rec1_permissible = self.rank_parser.is_permissible_overlap(
            record1["original_record"]["rank"]
        )
        is_rec2_permissible = self.rank_parser.is_permissible_overlap(
            record2["original_record"]["rank"]
        )

        # It's a hard conflict only if BOTH roles are non-permissible
        return not is_rec1_permissible and not is_rec2_permissible

    def _enrich_record(
        self, raw_record: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Enriches a single raw record with data needed for heuristics,
        such as the top-level parent ministry and a normalized rank.
        """
        # 1. Find the top-level parent organization (the ministry)
        parent_ministry_name = "UNKNOWN"
        org_url = raw_record.get("url")
        if org_url:
            # Use the repository to find the org and its ancestors
            org = self.orgs_repo.find_by_url(org_url)
            if org:
                # get_all_ancestors is sorted by depth, so the first is the top
                ancestors = self.orgs_repo.get_all_ancestors(org["id"])
                if ancestors:
                    parent_ministry_name = ancestors[0]["name"]
                else:
                    # This org has no parents, so it is the top level
                    parent_ministry_name = org["name"]

        # 2. Normalize the rank
        rank_score = self.rank_parser.parse_rank(raw_record.get("rank", ""))

        return {
            "start_date": raw_record["start_date"],
            "end_date": raw_record["end_date"],
            "rank_score": rank_score,
            "parent_ministry": parent_ministry_name,
            "original_record": raw_record,  # Keep for final output
        }

    def _has_temporal_conflict(
        self, record1: Dict[str, Any], record2: Dict[str, Any]
    ) -> bool:
        """Checks for temporal overlap between two jobs."""
        return (
            record1["start_date"] <= record2["end_date"]
            and record1["end_date"] >= record2["start_date"]
        )

    def _calculate_cohesion_score(
        self, new_record: Dict[str, Any], cluster_record: Dict[str, Any]
    ) -> int:
        """Calculates how well a new job fits with a previous job."""
        score = 0
        if (
            new_record["parent_ministry"]
            == cluster_record["parent_ministry"]
        ):
            score += self.COHESION_SCORES["SAME_PARENT_MINISTRY"]

        # --- UPDATED LOGIC: Handle Overlap vs. Succession ---
        if self._has_temporal_overlap(new_record, cluster_record):
            # This is a "Soft Conflict" because we already passed the
            # hard conflict check. Apply a penalty.
            score += self.COHESION_SCORES["PERMISSIBLE_OVERLAP_PENALTY"]
        else:
            # This is a sequential job change. Score based on rank and time gap.
            new_rank_score = new_record["rank_score"]
            cluster_rank_score = cluster_record["rank_score"]

            if new_rank_score > cluster_rank_score:
                score += self.COHESION_SCORES["LOGICAL_PROMOTION"]
            elif new_rank_score == cluster_rank_score:
                score += self.COHESION_SCORES["LATERAL_MOVE"]
            else:
                if cluster_rank_score - new_rank_score > 3:
                    score += self.COHESION_SCORES["ILLOGICAL_DEMOTION"]

            # Score based on time gap
            gap = new_record["start_date"] - cluster_record["end_date"]
            if timedelta(days=0) <= gap < timedelta(days=30):
                score += self.COHESION_SCORES["IMMEDIATE_SUCCESSION"]
            elif timedelta(days=30) <= gap < timedelta(days=180):
                score += self.COHESION_SCORES["QUICK_SUCCESSION"]

        return score

    def cluster_employment_records(
        self, raw_records: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """
        The main public method. Takes a list of raw employment records for a
        single name and clusters them into distinct people.
        """
        # 1. Enrich all records with data from the database
        enriched_records = []
        for rec in raw_records:
            enriched = self._enrich_record(rec)
            if enriched:
                enriched_records.append(enriched)

        # 2. Sort records chronologically to process them in order
        sorted_records = sorted(
            enriched_records, key=lambda x: x["start_date"]
        )

        clusters: List[List[Dict[str, Any]]] = []

        for record in sorted_records:
            best_cluster_index = -1
            max_cluster_score = -999  # Start with a very low score

            for i, cluster in enumerate(clusters):
                is_compatible = True
                for cluster_record in cluster:
                    if self._is_hard_conflict(record, cluster_record):
                        is_compatible = False
                        break
                if not is_compatible:
                    continue  # This cluster is impossible, skip it
                # If no hard conflicts, calculate the cohesion score.
                # The score function will handle soft conflicts.
                current_cluster_score = 0
                for cluster_record in cluster:
                    current_cluster_score += self._calculate_cohesion_score(
                        record, cluster_record
                    )

                if current_cluster_score > max_cluster_score:
                    max_cluster_score = current_cluster_score
                    best_cluster_index = i

                # Calculate cohesion score against previous jobs in the cluster
                for cluster_record in cluster:
                    if record["start_date"] > cluster_record["end_date"]:
                        current_cluster_score += (
                            self._calculate_cohesion_score(
                                record, cluster_record
                            )
                        )

                if current_cluster_score > max_cluster_score:
                    max_cluster_score = current_cluster_score
                    best_cluster_index = i

            # Decide where to place the record
            if (
                best_cluster_index != -1
                and max_cluster_score >= self.MINIMUM_COHESION_THRESHOLD
            ):
                clusters[best_cluster_index].append(record)
            else:
                clusters.append([record])

        # Return the clusters, but with the original records for full detail
        final_clusters = [
            [job["original_record"] for job in cluster]
            for cluster in clusters
        ]
        return final_clusters
