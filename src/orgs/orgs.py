from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Set, NamedTuple, Any
from urllib.parse import urljoin, urlparse, urlunparse
from contextlib import contextmanager
import concurrent.futures
import os
import pickle
import re
import threading
import time
import urllib.parse
import traceback
import json

import pandas as pd
import requests
from bs4 import BeautifulSoup
from loguru import logger
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from sqlite3 import Connection, connect


class OrgType(Enum):
    MINISTRY = auto()
    DEPARTMENT = auto()
    SUBDEPARTMENT = auto()
    NESTED_DEPARTMENT = auto()
    UNKNOWN = auto()


class URLAnalysis(NamedTuple):
    matched: bool
    org_type: OrgType
    ministry: Optional[str] = None
    department_type: Optional[str] = None
    department: Optional[str] = None
    subdepartment: Optional[str] = None
    nested_departments: List[str] = field(default_factory=list)


@dataclass
class OrgNode:
    url: str
    name: Optional[str] = None
    org_type: OrgType = OrgType.UNKNOWN
    parent_url: Optional[str] = None
    children_urls: Set[str] = field(default_factory=set)
    metadata: Dict = field(default_factory=dict)
    depth: int = 0

    def add_child(self, child_url: str) -> None:
        self.children_urls.add(child_url)

    def to_dict(self) -> Dict:
        return {
            "url": self.url,
            "name": self.name,
            "org_type": self.org_type.name,
            "parent_url": self.parent_url,
            "children_count": len(self.children_urls),
            "depth": self.depth,
            "metadata": self.metadata,
        }


class ScrapingError(Exception):
    """Custom exception for scraping related errors"""

    pass


class RateLimiter:
    def __init__(self, requests_per_second: float = 2.0):
        self.delay = 1.0 / requests_per_second
        self.last_request = 0.0
        self._lock = threading.Lock()

    @contextmanager
    def limit(self):
        with self._lock:
            now = time.time()
            time_passed = now - self.last_request
            if time_passed < self.delay:
                time.sleep(self.delay - time_passed)
            self.last_request = time.time()
            yield


class RequestsManager:
    def __init__(
        self,
        rate_limit: float = 2.0,
        timeout: int = 10,
        max_retries: int = 3,
        backoff_factor: float = 0.3,
        retry_status_forcelist: Set[int] = {500, 502, 503, 504},
    ):
        self.rate_limiter = RateLimiter(rate_limit)
        self.timeout = timeout
        self.session = self._create_session(
            max_retries, backoff_factor, retry_status_forcelist
        )
        self.failed_urls: Dict[str, Dict] = {}
        self._failed_urls_lock = threading.Lock()

    def _create_session(
        self,
        max_retries: int,
        backoff_factor: float,
        retry_status_forcelist: Set[int],
    ) -> requests.Session:
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=retry_status_forcelist,
            allowed_methods={"GET", "HEAD"},
        )
        session = requests.Session()
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def get(self, url: str) -> requests.Response:
        with self.rate_limiter.limit():
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                self._record_failure(url, e)
                raise ScrapingError(f"Failed to fetch {url}: {str(e)}")

    def _record_failure(self, url: str, error: Exception) -> None:
        with self._failed_urls_lock:
            if url not in self.failed_urls:
                self.failed_urls[url] = {
                    "first_error": str(error),
                    "first_error_time": time.time(),
                    "retry_count": 1,
                    "errors": [str(error)],
                }
            else:
                self.failed_urls[url]["retry_count"] += 1
                self.failed_urls[url]["errors"].append(str(error))

    def export_failures(self, export_dir: str) -> None:
        with self._failed_urls_lock:
            if not self.failed_urls:
                return
            df = pd.DataFrame.from_dict(self.failed_urls, orient="index")
            output_path = os.path.join(export_dir, "scraping_failures.csv")
            df.to_csv(output_path)
            logger.info(f"Exported scraping failures to {output_path}")


class OrgChartMapper:
    BASE_URL = "https://www.sgdi.gov.sg"

    def __init__(self, db_path: str, export_dir: str):
        self.db_path = db_path
        self.export_dir = export_dir
        self.org_nodes: Dict[str, OrgNode] = {}
        self.visited_urls: Set[str] = set()
        self.unmatched_urls: Dict[str, Dict] = {}
        self.requests = RequestsManager(
            rate_limit=2.0,
            timeout=15,
            max_retries=3,
            backoff_factor=0.5,
        )
        self._setup()

    def _setup(self) -> None:
        self._setup_logging()
        self._compile_patterns()

    def _setup_logging(self) -> None:
        log_path = os.path.join(self.export_dir, "org_mapper.log")
        logger.add(log_path, rotation="1 day", retention="7 days")

    def _compile_patterns(self) -> None:
        ministry_part = r"ministries/([^/]+)"
        dept_type_part = r"(statutory-boards|departments|committees|others)"
        dept_name_part = r"([^/]+)"
        dept_pattern = r"(?:/departments/[^/]+)*"  # Remove (?i) from here

        self.URL_PATTERNS = {
            # Add (?i) at start of entire pattern
            OrgType.MINISTRY: re.compile(
                f"(?i){self.BASE_URL}/{ministry_part}/?$"
            ),
            # Add (?i) at start of entire pattern
            OrgType.DEPARTMENT: re.compile(
                f"(?i){self.BASE_URL}/{ministry_part}/{dept_type_part}/{dept_name_part}{dept_pattern}/?$"
            ),
        }

    def get_conn(self) -> Connection:
        return connect(self.db_path)

    def get_last_updated(self, conn: Optional[Connection] = None) -> str:
        conn = conn or self.get_conn()
        cur = conn.cursor()
        res = cur.execute(
            "SELECT DISTINCT(date_created) FROM names ORDER BY date_created DESC LIMIT 1"
        )
        found_date = res.fetchall()[0][0]
        logger.info(f"Last updated: {found_date}")
        return found_date

    def normalize_url(self, url: str) -> str:
        url = url.strip()
        if url.startswith("/"):
            url = url[1:]
        if "https:/" in url and not url.startswith("https://"):
            url = url.replace("https:/", "https://")
        if not url.startswith("http"):
            url = f"https://{url}"

        parsed = urllib.parse.urlparse(url)
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path.rstrip("/"),
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )

    def analyze_url(self, url: str) -> URLAnalysis:
        try:
            normalized_url = self.normalize_url(url)
            logger.bind(
                original_url=url, normalized_url=normalized_url
            ).debug(f"Processing URL {normalized_url}")

            path_parts = urlparse(normalized_url).path.strip("/").split("/")

            # Check for ministry pattern
            ministry_match = self.URL_PATTERNS[OrgType.MINISTRY].match(
                normalized_url
            )
            if ministry_match:
                return URLAnalysis(
                    matched=True,
                    org_type=OrgType.MINISTRY,
                    ministry=ministry_match.group(1),
                )

            # Check for department pattern
            dept_match = self.URL_PATTERNS[OrgType.DEPARTMENT].match(
                normalized_url
            )
            if dept_match:
                ministry = dept_match.group(1)
                dept_type = dept_match.group(2)
                base_dept = dept_match.group(3)

                dept_layers = self._extract_department_layers(path_parts)
                org_type = (
                    OrgType.DEPARTMENT
                    if not dept_layers
                    else OrgType.NESTED_DEPARTMENT
                )

                return URLAnalysis(
                    matched=True,
                    org_type=org_type,
                    ministry=ministry,
                    department_type=dept_type,
                    department=base_dept,
                    nested_departments=dept_layers,
                )

        except Exception as e:
            logger.error(f"Error analyzing URL {url}: {str(e)}")

        self._record_unmatched_url(url)
        return URLAnalysis(matched=False, org_type=OrgType.UNKNOWN)

    def infer_parent_url(self, url: str) -> Optional[str]:
        """Infer parent URL with support for arbitrary depth"""
        path_parts = [p for p in url.split("/") if p]

        # Find the last occurrence of 'departments' (case-insensitive)
        dept_indices = [
            i
            for i, part in enumerate(path_parts)
            if part.lower() == "departments"
        ]

        if dept_indices:
            # If we find a departments indicator, the parent is everything up to its last occurrence
            last_dept_idx = dept_indices[-1]
            if last_dept_idx > 0:  # Ensure we have parts before this
                return "/".join([""] + path_parts[:last_dept_idx])

        # If no departments found, try to find the parent based on standard structure
        analysis = self.analyze_url(url)
        if analysis.matched:
            if analysis.org_type == OrgType.MINISTRY:
                return None
            elif analysis.org_type == OrgType.DEPARTMENT:
                return f"{self.BASE_URL}/ministries/{analysis.ministry}"
            elif analysis.org_type == OrgType.NESTED_DEPARTMENT:
                # Remove the last two parts (departments/name) from the URL
                parts = url.rstrip("/").split("/")
                return "/".join(parts[:-2])

        # If we can't determine the parent, return one level up
        if len(path_parts) > 1:
            return "/".join([""] + path_parts[:-1])

        return None

    def discover_child_urls(self, url: str) -> Set[str]:
        try:
            response = self.requests.get(url)
            soup = BeautifulSoup(response.text, "html.parser")
            child_urls = set()

            for link in soup.find_all("a", href=True):
                href = link["href"]
                full_url = urljoin(self.BASE_URL, href)

                if not full_url.startswith(self.BASE_URL):
                    continue

                normalized_url = self.normalize_url(full_url)
                child_urls.add(normalized_url)

            return child_urls

        except ScrapingError as e:
            logger.warning(
                f"Failed to discover child URLs for {url}: {str(e)}"
            )
            return set()
        except Exception as e:
            logger.error(
                f"Unexpected error discovering child URLs for {url}: {str(e)}"
            )
            return set()

    def _extract_department_layers(
        self, path_parts: List[str]
    ) -> List[str]:
        dept_layers = []
        in_departments = False

        for part in path_parts[1:]:
            if part.lower() == "departments":
                in_departments = True
            elif in_departments:
                dept_layers.append(part)
                in_departments = False

        return dept_layers

    def _record_unmatched_url(
        self, url: str, details: Optional[Dict] = None
    ) -> None:
        if url in self.unmatched_urls:
            return

        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]

        org_structure = {
            "full_path": parsed.path,
            "path_parts": path_parts,
            "path_length": len(path_parts),
            "query_params": parsed.query,
            "fragment": parsed.fragment,
            "discovered_from": None,
            "potential_type": self._guess_org_type(path_parts),
            "case_variations": [
                p for p in path_parts if p.lower() == "departments"
            ],
            "original_case": "/".join(path_parts),
        }

        if details:
            org_structure.update(details)

        self.unmatched_urls[url] = org_structure
        logger.warning(
            f"Unmatched URL pattern: {url}\nStructure: {org_structure}"
        )

    def _guess_org_type(self, path_parts: List[str]) -> str:
        keywords = {
            "ministry": {"ministries", "ministry"},
            "department": {
                "departments",
                "department",
                "statutory-boards",
                "committees",
                "divisions",
            },
            "division": {
                "divisions",
                "division",
                "branches",
                "units",
                "sections",
            },
        }

        lower_parts = [p.lower() for p in path_parts]

        # Check for direct keyword matches
        for part in lower_parts:
            for org_type, type_keywords in keywords.items():
                if part in type_keywords:
                    return org_type

        # Infer from structure
        if "ministries" in lower_parts:
            depth = len(path_parts) - lower_parts.index("ministries")
            if depth == 2:
                return "ministry"
            elif depth == 4:
                return "department"
            elif depth > 4:
                return "nested_department"

        return "unknown"

    def process_url_batch(
        self, urls: List[str], max_workers: int = 10
    ) -> None:
        def process_single_url(url: str) -> Optional[Dict[str, Any]]:
            try:
                if url in self.visited_urls:
                    return None

                self.visited_urls.add(url)
                normalized_url = self.normalize_url(url)
                analysis = self.analyze_url(normalized_url)

                if normalized_url not in self.org_nodes:
                    self.org_nodes[normalized_url] = OrgNode(
                        url=normalized_url, org_type=analysis.org_type
                    )

                node = self.org_nodes[normalized_url]

                try:
                    response = self.requests.get(normalized_url)
                    soup = BeautifulSoup(response.text, "html.parser")

                    title_div = soup.find("div", class_="agency-title")
                    if title_div:
                        node.name = title_div.get_text(" : ")

                    contact_div = soup.find("div", class_="contact-info")
                    if contact_div:
                        node.metadata["contact_info"] = (
                            contact_div.get_text(strip=False)
                        )

                    desc_div = soup.find("div", class_="agency-description")
                    if desc_div:
                        node.metadata["description"] = desc_div.get_text(
                            strip=False
                        )

                except ScrapingError as e:
                    logger.warning(
                        f"Scraping error for {normalized_url}: {str(e)}"
                    )
                    node.metadata["scraping_error"] = str(e)

                parent_url = self.infer_parent_url(normalized_url)
                if parent_url:
                    parent_url = self.normalize_url(parent_url)
                    if parent_url not in self.org_nodes:
                        self.org_nodes[parent_url] = OrgNode(url=parent_url)
                    node.parent_url = parent_url
                    self.org_nodes[parent_url].add_child(normalized_url)

                child_urls = self.discover_child_urls(normalized_url)
                node.children_urls.update(child_urls)

                return {"url": normalized_url, "child_urls": child_urls}

            except Exception as e:
                logger.error(f"Error processing {url}: {str(e)}")
                return None

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers
        ) as executor:
            future_to_url = {
                executor.submit(process_single_url, url): url
                for url in urls
            }

            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    if result and result["child_urls"]:
                        new_urls = [
                            u
                            for u in result["child_urls"]
                            if u not in self.visited_urls
                        ]
                        if new_urls:
                            self.process_url_batch(new_urls, max_workers)
                except Exception as e:
                    logger.error(
                        f"Error processing future for {url}: {str(e)}"
                    )

    def build_org_chart(self, initial_urls: List[str]) -> pd.DataFrame:
        logger.info("Starting organizational chart building process")

        try:
            self.process_url_batch(initial_urls, max_workers=5)
            org_data = [node.to_dict() for node in self.org_nodes.values()]
            df = pd.DataFrame(org_data)

            self.export_unmatched_analysis()
            self.requests.export_failures(self.export_dir)

            return df

        except Exception as e:
            logger.error(f"Error building org chart: {str(e)}")
            self._save_partial_results()
            raise

    def export_unmatched_analysis(self) -> None:
        """Export analysis of unmatched URLs with enhanced pattern discovery"""
        if not self.unmatched_urls:
            return

        try:
            # Convert unmatched URLs data to DataFrame
            df = pd.DataFrame.from_dict(self.unmatched_urls, orient="index")

            # Add analysis columns
            df["path_depth"] = df["path_parts"].apply(len)
            df["has_ministry"] = df["path_parts"].apply(
                lambda x: "ministries" in [p.lower() for p in x]
            )
            df["has_department"] = df["path_parts"].apply(
                lambda x: "departments" in [p.lower() for p in x]
                or "statutory-boards" in [p.lower() for p in x]
            )

            # Export main analysis
            output_path = os.path.join(
                self.export_dir, "unmatched_urls_analysis.csv"
            )
            df.to_csv(output_path)
            logger.info(
                f"Exported unmatched URLs analysis to {output_path}"
            )

            # Generate pattern analysis
            pattern_counts = defaultdict(int)
            pattern_examples = defaultdict(list)

            for url, data in self.unmatched_urls.items():
                path_parts = data.get("path_parts", [])

                # Create pattern representation
                pattern = []
                for part in path_parts:
                    if part.lower() == "ministries":
                        pattern.append("<ministry>")
                    elif part.lower() in [
                        "departments",
                        "statutory-boards",
                        "committees",
                        "others",
                    ]:
                        pattern.append(f"<{part.lower()}>")
                    elif part.lower() == "departments":
                        pattern.append("<department>")
                    else:
                        pattern.append("<name>")

                pattern_str = "/".join(pattern)
                pattern_counts[pattern_str] += 1
                if (
                    len(pattern_examples[pattern_str]) < 3
                ):  # Store up to 3 examples per pattern
                    pattern_examples[pattern_str].append(url)

            # Create pattern analysis DataFrame
            pattern_data = []
            for pattern, count in pattern_counts.items():
                pattern_data.append(
                    {
                        "pattern": pattern,
                        "count": count,
                        "examples": "\n".join(pattern_examples[pattern]),
                    }
                )

            pattern_df = pd.DataFrame(pattern_data)
            pattern_df.sort_values("count", ascending=False, inplace=True)

            # Export pattern analysis
            pattern_path = os.path.join(
                self.export_dir, "url_patterns_analysis.csv"
            )
            pattern_df.to_csv(pattern_path, index=False)
            logger.info(f"Exported URL pattern analysis to {pattern_path}")

            # Generate summary statistics
            summary_data = {
                "total_unmatched_urls": len(self.unmatched_urls),
                "unique_patterns": len(pattern_counts),
                "avg_path_depth": df["path_depth"].mean(),
                "max_path_depth": df["path_depth"].max(),
                "urls_with_ministry": df["has_ministry"].sum(),
                "urls_with_department": df["has_department"].sum(),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            # Export summary
            summary_path = os.path.join(
                self.export_dir, "unmatched_urls_summary.json"
            )
            with open(summary_path, "w") as f:
                json.dump(summary_data, f, indent=2)
            logger.info(
                f"Exported unmatched URLs summary to {summary_path}"
            )

        except Exception as e:
            logger.error(
                f"Error exporting unmatched analysis: {str(e)}\n{traceback.format_exc()}"
            )
            # Try to save partial results if possible
            try:
                error_path = os.path.join(
                    self.export_dir, "unmatched_analysis_error.txt"
                )
                with open(error_path, "w") as f:
                    f.write(
                        f"Error: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
                    )
                logger.info(f"Saved error details to {error_path}")
            except Exception:
                pass

    def _save_partial_results(self) -> None:
        if not self.org_nodes:
            return

        partial_data = [node.to_dict() for node in self.org_nodes.values()]
        partial_df = pd.DataFrame(partial_data)
        partial_path = os.path.join(
            self.export_dir, "partial_org_chart.csv"
        )
        partial_df.to_csv(partial_path, index=False)
        logger.info(f"Saved partial results to {partial_path}")

    def run_pipeline(self) -> None:
        try:
            if self.load_state():
                logger.info("Resumed from previous state")

            conn = self.get_conn()
            last_updated = self.get_last_updated(conn)

            initial_urls = pd.read_sql(
                "SELECT DISTINCT url FROM names WHERE date_created = :found_date",
                conn,
                params={"found_date": last_updated},
            )["url"].tolist()

            org_chart_df = self.build_org_chart(initial_urls)
            self.export_org_chart(org_chart_df)
            self.save_state()

        except Exception as e:
            logger.error(f"Pipeline error: {str(e)}")
            self.save_state()
            raise
        finally:
            self.requests.export_failures(self.export_dir)

    def export_org_chart(
        self, df: pd.DataFrame, filename: str = "org_chart.csv"
    ) -> None:
        output_path = os.path.join(self.export_dir, filename)
        df.to_csv(output_path, index=False)
        logger.info(f"Exported organizational chart to {output_path}")

    def save_state(self) -> None:
        state_path = os.path.join(self.export_dir, "org_state.pkl")
        with open(state_path, "wb") as f:
            pickle.dump(self.org_nodes, f)
        logger.info(f"Saved organizational state to {state_path}")

    def load_state(self) -> bool:
        state_path = os.path.join(self.export_dir, "org_state.pkl")
        if os.path.exists(state_path):
            with open(state_path, "rb") as f:
                self.org_nodes = pickle.load(f)
            logger.info(f"Loaded organizational state from {state_path}")
            return True
        return False


def main():
    DB_PATH = "data/sgdb.db"
    EXPORT_DIR = "data/sgdi_processed"

    mapper = OrgChartMapper(DB_PATH, EXPORT_DIR)
    mapper.run_pipeline()


if __name__ == "__main__":
    main()
