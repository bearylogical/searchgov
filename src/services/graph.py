import networkx as nx
from typing import List, Dict, Any, Optional, Union
from src.services.query import QueryService
from src.services.organisations import OrganisationService
from loguru import logger
from datetime import datetime
from itertools import combinations
from collections import defaultdict


class GraphService:
    def __init__(
        self,
        query_service: QueryService,
        orgs_service: OrganisationService,
    ):
        self.query_service = query_service
        self.orgs_service = orgs_service
        self.logger = logger
        self._graph_cache = None
        self._cache_date = None
        self._full_graph_cache = None  # --- ADDED: Cache for the new graph
        self._colleague_graph_cache = None

    async def _build_colleague_graph(self) -> nx.Graph:
        """
        Builds a time-aware, person-to-person graph where an edge
        represents a direct, overlapping employment period at the same org.

        This is computationally intensive and should be cached.
        """
        if self._colleague_graph_cache:
            self.logger.info("Returning cached colleague graph.")
            return self._colleague_graph_cache

        self.logger.info("Building new colleague graph...")
        all_data = await self.query_service.get_all_employment_data()

        # Step 1: Group all employments by organization
        org_employees = defaultdict(list)
        for record in all_data:
            org_employees[record["org_id"]].append(record)

        # Step 2: Create a person-only graph
        G_colleagues = (
            nx.Graph()
        )  # Undirected, a colleague relationship is mutual

        # Add all people as nodes first, using prefixed IDs
        all_person_info = {
            (r["person_id"], r["person_name"]) for r in all_data
        }
        for pid, pname in all_person_info:
            G_colleagues.add_node(f"person_{pid}", name=pname)

        # Step 3: For each org, find overlapping employment between all pairs
        for org_id, employments in org_employees.items():
            # Use combinations to efficiently get all unique pairs of employees
            for p1_record, p2_record in combinations(employments, 2):
                p1_id = p1_record["person_id"]
                p2_id = p2_record["person_id"]

                # Classic interval overlap check
                p1_starts_before_p2_ends = (
                    p1_record["start_date"] <= p2_record["end_date"]
                )
                p2_starts_before_p1_ends = (
                    p2_record["start_date"] <= p1_record["end_date"]
                )

                if p1_starts_before_p2_ends and p2_starts_before_p1_ends:
                    # Their time at this org overlapped! Create an edge.
                    node1 = f"person_{p1_id}"
                    node2 = f"person_{p2_id}"

                    # We can store the org as an attribute for more context
                    if G_colleagues.has_edge(node1, node2):
                        # If they were colleagues at multiple orgs, add to the list
                        G_colleagues.edges[node1, node2]["orgs"].append(
                            org_id
                        )
                    else:
                        G_colleagues.add_edge(node1, node2, orgs=[org_id])

        self.logger.info(
            f"Colleague graph built with {G_colleagues.number_of_nodes()} nodes and {G_colleagues.number_of_edges()} edges."
        )
        self._colleague_graph_cache = G_colleagues
        return G_colleagues

    async def build_full_history_graph(self) -> nx.MultiDiGraph:
        """
        Builds a NetworkX graph from the entire history of employment data.
        This implementation creates unique node IDs by prefixing them with
        their type to prevent collisions between person and organization IDs.
        """
        if self._full_graph_cache:
            self.logger.info("Returning cached full history graph.")
            return self._full_graph_cache

        try:
            all_data = await self.query_service.get_all_employment_data()
            org_hierarchy = (
                await self.orgs_service.get_organization_hierarchy()
            )

            G = nx.MultiDiGraph()

            # Step 2: Add nodes using prefixed IDs
            all_person_info = {
                (r["person_id"], r["person_name"]) for r in all_data
            }
            for pid, pname in all_person_info:
                # Use a prefixed ID like "person_42"
                G.add_node(f"person_{pid}", type="person", name=pname)

            for org in org_hierarchy:
                # Use a prefixed ID like "org_42"
                G.add_node(
                    f"org_{org['id']}",
                    type="organization",
                    name=org["name"],
                )

            # Step 3: Add employment edges using prefixed IDs
            for record in all_data:
                G.add_edge(
                    f"person_{record['person_id']}",
                    f"org_{record['org_id']}",
                    relationship="employed_at",
                    rank=record["rank"],
                    start_date=record["start_date"],
                    end_date=record["end_date"],
                )

            # Step 4: Add hierarchy edges using prefixed IDs
            for org in org_hierarchy:
                if org.get("parent_org_id"):
                    G.add_edge(
                        f"org_{org['id']}",
                        f"org_{org['parent_org_id']}",
                        relationship="subunit_of",
                    )

            self._full_graph_cache = G
            return G

        except Exception as e:
            self.logger.error(f"Error building full history graph: {e}")
            raise

    async def build_networkx_graph(
        self, target_date: str = None
    ) -> nx.MultiDiGraph:
        """
        Builds a NetworkX graph where nodes are integer IDs for people and
        organizations, and names are stored as attributes.
        """
        if self._graph_cache and self._cache_date == target_date:
            return self._graph_cache

        try:
            # Step 1: Get data (assuming it includes IDs)
            snapshot = await self.query_service.get_network_snapshot(
                target_date
            )
            org_hierarchy = (
                await self.orgs_service.get_organization_hierarchy()
            )

            G = nx.MultiDiGraph()

            # Step 2: Add person and org nodes using their IDs
            for record in snapshot:
                G.add_node(
                    record["person_id"],
                    type="person",
                    name=record["person_name"],
                )
            for org in org_hierarchy:
                G.add_node(org["id"], type="organization", name=org["name"])

            # Step 3: Add employment edges using IDs
            for record in snapshot:
                G.add_edge(
                    record["person_id"],
                    record["org_id"],
                    relationship="employed_at",
                    rank=record["rank"],
                    start_date=record["start_date"],
                    end_date=record["end_date"],
                )

            # Step 4: Add hierarchy edges using IDs
            for org in org_hierarchy:
                if org.get("parent_org_id"):
                    # The parent node should already exist from Step 2
                    G.add_edge(
                        org["id"],
                        org["parent_org_id"],
                        relationship="subunit_of",
                    )

            self._graph_cache = G
            self._cache_date = target_date
            return G

        except KeyError as e:
            self.logger.error(
                f"Missing a required ID (e.g., 'person_id', 'org_id') in the data snapshot. Error: {e}"
            )
            raise
        except Exception as e:
            self.logger.error(f"Error building NetworkX graph: {e}")
            raise

    async def find_shortest_path(
        self,
        person1_ids: Union[int, List[int]],
        person2_ids: Union[int, List[int]],
        people_only: bool = True,
        ids_only: bool = False,
    ) -> List[str]:
        """
        Finds the shortest path between two people or groups of people
        across the entire history of the data. This is time-agnostic.

        Args:
            person1_ids: A single int ID or a list of int IDs for the start person(s).
            person2_ids: A single int ID or a list of int IDs for the end person(s).
            people_only: If True, the returned path will be filtered to only
                         include the names of people. Defaults to False.

        Returns:
            A list of names for the nodes in the shortest path found.
        """
        source_ids_int = (
            [person1_ids] if isinstance(person1_ids, int) else person1_ids
        )
        target_ids_int = (
            [person2_ids] if isinstance(person2_ids, int) else person2_ids
        )

        # Create the prefixed IDs (e.g., 101 -> "person_101")
        source_ids = [f"person_{pid}" for pid in source_ids_int]
        target_ids = [f"person_{pid}" for pid in target_ids_int]

        # Use the new time-agnostic graph builder
        G = await self.build_full_history_graph()
        shortest_path_ids = None

        # The rest of the logic remains the same...
        valid_source_ids = [pid for pid in source_ids if pid in G]
        valid_target_ids = [pid for pid in target_ids if pid in G]

        if not valid_source_ids or not valid_target_ids:
            self.logger.warning(
                f"No valid source or target IDs found in the graph. "
                f"Sources given: {source_ids}, Targets given: {target_ids}"
            )
            return []

        for source_id in valid_source_ids:
            for target_id in valid_target_ids:
                if source_id == target_id:
                    if shortest_path_ids is None:
                        shortest_path_ids = [source_id]
                    continue

                try:
                    current_path_ids = nx.shortest_path(
                        G.to_undirected(),
                        source=source_id,
                        target=target_id,
                    )

                    if shortest_path_ids is None or len(
                        current_path_ids
                    ) < len(shortest_path_ids):
                        shortest_path_ids = current_path_ids

                except nx.NetworkXNoPath:
                    continue
                except Exception as e:
                    self.logger.error(
                        f"Error finding shortest path for IDs ({source_id}, {target_id}): {e}"
                    )
                    continue

        if shortest_path_ids is None:
            self.logger.info(
                f"No path found between any of {valid_source_ids} and any of {valid_target_ids}."
            )
            return []

        # Now, we filter the full path based on the 'people_only' flag
        if people_only:
            # Create a new list containing only the nodes that are people
            path_ids_to_use = [
                node_id
                for node_id in shortest_path_ids
                if self._full_graph_cache.nodes[node_id].get("type")
                == "person"
            ]
        else:
            # Use the full, unfiltered path with all the "stepping stones"
            path_ids_to_use = shortest_path_ids
        if ids_only:
            # If ids_only is True, return the IDs directly
            return path_ids_to_use
        else:
            # Convert the final list of IDs to names
            path_names = [
                self._full_graph_cache.nodes[node_id]["name"]
                for node_id in path_ids_to_use
            ]
            # include additional metadata about the person
            # self.query_service.find_person_by_id

            return path_names

    async def find_shortest_temporal_path(
        self,
        person1_ids: Union[int, List[int]],
        person2_ids: Union[int, List[int]],
        ids_only: bool = False,
    ) -> List[str]:
        """
        Finds the shortest path of people who were verifiably colleagues,
        based on overlapping employment dates. It can find the shortest path
        between two individuals or between two groups of people.

        Args:
            person1_ids: A single int ID or a list of int IDs for the start person(s).
            person2_ids: A single int ID or a list of int IDs for the end person(s).

        Returns:
            A list of names for the people in the shortest temporal path found.
            Returns an empty list if no such path exists.
        """
        # Step 1: Build or retrieve the specialized colleague graph
        colleague_G = await self._build_colleague_graph()
        full_G = (
            await self.build_full_history_graph()
        )  # Ensures we can get org names

        # Step 2: Normalize inputs and format node IDs
        source_ids_int = (
            [person1_ids] if isinstance(person1_ids, int) else person1_ids
        )
        target_ids_int = (
            [person2_ids] if isinstance(person2_ids, int) else person2_ids
        )
        source_nodes = [f"person_{pid}" for pid in source_ids_int]
        target_nodes = [f"person_{pid}" for pid in target_ids_int]

        # Step 3: Filter for nodes that actually exist in the colleague graph
        valid_source_nodes = [
            node for node in source_nodes if node in colleague_G
        ]
        valid_target_nodes = [
            node for node in target_nodes if node in colleague_G
        ]

        if not valid_source_nodes or not valid_target_nodes:
            self.logger.warning(
                f"No valid source or target IDs found in the colleague graph. "
                f"Sources given: {source_ids_int}, Targets given: {target_ids_int}"
            )
            return []
        # Step 4: Find the shortest path among all possible pairs
        shortest_person_path_ids = None

        # ... (This logic is identical to the previous version) ...
        for source_node in valid_source_nodes:
            for target_node in valid_target_nodes:
                if source_node == target_node:
                    if shortest_person_path_ids is None:
                        shortest_person_path_ids = [source_node]
                    continue
                try:
                    current_path_ids = nx.shortest_path(
                        colleague_G, source=source_node, target=target_node
                    )
                    if shortest_person_path_ids is None or len(
                        current_path_ids
                    ) < len(shortest_person_path_ids):
                        shortest_person_path_ids = current_path_ids
                except nx.NetworkXNoPath:
                    continue
                except Exception as e:
                    self.logger.error(
                        f"Error finding temporal path for ({source_node}, {target_node}): {e}"
                    )
                    continue

        # Step 5: If a path was found, convert IDs to names
        if not shortest_person_path_ids:
            self.logger.info(
                f"No valid temporal path found between any of {valid_source_nodes} and any of {valid_target_nodes}."
            )
            return []

        # Step 4: Build a structured representation of the full path
        structured_path = []

        # Helper to safely parse the integer ID from a prefixed node ID
        def get_int_id(prefixed_id):
            return int(prefixed_id.split("_")[1])

        # Add the first person
        first_person_id = get_int_id(shortest_person_path_ids[0])
        structured_path.append({"type": "person", "id": first_person_id})

        # If path is longer than one person, weave in the orgs
        if len(shortest_person_path_ids) > 1:
            for i in range(len(shortest_person_path_ids) - 1):
                p1_node_id = shortest_person_path_ids[i]
                p2_node_id = shortest_person_path_ids[i + 1]

                edge_data = colleague_G.edges[p1_node_id, p2_node_id]
                connecting_org_id = edge_data["orgs"][0]
                p2_id = get_int_id(p2_node_id)

                structured_path.append(
                    {"type": "org", "id": connecting_org_id}
                )
                structured_path.append({"type": "person", "id": p2_id})

        # Step 5: Format the output based on the 'ids_only' flag
        if ids_only:
            final_path_names = []
            for item in structured_path:
                if item["type"] == "person":
                    node_id = f"person_{item['id']}"
                    if ids_only:
                        final_path_names.append(node_id)
                    else:
                        final_path_names.append(
                            colleague_G.nodes[node_id]["name"]
                        )
                else:  # type is 'org'
                    node_id = f"org_{item['id']}"
                    if ids_only:
                        final_path_names.append(node_id)
                    else:
                        final_path_names.append(
                            full_G.nodes[node_id]["name"]
                        )

            return final_path_names

    async def calculate_centrality_metrics(
        self, target_date: str = None
    ) -> Dict[str, Dict]:
        """
        Calculate centrality metrics on a graph of people connected through
        the full organizational hierarchy.
        """
        G = await self.build_networkx_graph(target_date)
        if not G:
            return {}

        # Create a person-only graph based on the full connectivity
        person_graph = nx.Graph()
        persons = {
            n for n, d in G.nodes(data=True) if d["type"] == "person"
        }

        # Add nodes to the person_graph
        for person in persons:
            person_graph.add_node(person)

        # Find connections between all pairs of people
        # This is more computationally intensive but far more accurate
        for person1, person2 in combinations(persons, 2):
            # Check if a path exists between them in the main graph
            if nx.has_path(G.to_undirected(), person1, person2):
                person_graph.add_edge(person1, person2)

        if person_graph.number_of_edges() == 0:
            self.logger.warning(
                "No connections found between people for centrality calculation."
            )
            return {}

        try:
            # Now calculate centrality on the accurate person-to-person graph
            return {
                "betweenness_centrality": nx.betweenness_centrality(
                    person_graph
                ),
                "degree_centrality": nx.degree_centrality(person_graph),
                "closeness_centrality": nx.closeness_centrality(
                    person_graph
                ),
            }
        except Exception as e:
            self.logger.error(f"Error calculating centrality: {e}")
            return {}
