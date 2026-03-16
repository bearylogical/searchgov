import networkx as nx
from datetime import date as date_type
from typing import List, Dict, Any, Union
from src.services.query import QueryService
from src.services.organisations import OrganisationService
from loguru import logger
from itertools import combinations
from collections import defaultdict, deque

_MAX_DATE = date_type.max  # sentinel for open-ended employment


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

                # Classic interval overlap check.
                # Treat NULL end_date (still employed) as MAX_DATE so
                # comparisons never raise TypeError against None.
                p1_end = p1_record["end_date"] or _MAX_DATE
                p2_end = p2_record["end_date"] or _MAX_DATE
                p1_starts_before_p2_ends = (
                    p1_record["start_date"] <= p2_end
                )
                p2_starts_before_p1_ends = (
                    p2_record["start_date"] <= p1_end
                )

                if p1_starts_before_p2_ends and p2_starts_before_p1_ends:
                    # Their time at this org overlapped! Create an edge.
                    node1 = f"person_{p1_id}"
                    node2 = f"person_{p2_id}"

                    # Compute the actual overlap window
                    overlap_start = max(
                        p1_record["start_date"], p2_record["start_date"]
                    )
                    overlap_end = min(p1_end, p2_end)
                    overlap_info = {
                        "org_id": org_id,
                        "overlap_start": overlap_start,
                        "overlap_end": overlap_end,
                    }

                    if G_colleagues.has_edge(node1, node2):
                        # Multiple orgs — append overlap info
                        G_colleagues.edges[node1, node2][
                            "overlaps"
                        ].append(overlap_info)
                    else:
                        G_colleagues.add_edge(
                            node1, node2, overlaps=[overlap_info]
                        )

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

    def _bfs_backwards_temporal(
        self,
        G: nx.Graph,
        source: str,
        target: str,
    ):
        """
        BFS that finds the shortest colleague path going strictly backwards
        in time.  At each hop the chosen overlap must end *at or before* the
        time boundary inherited from the previous hop, so the chain of
        connections walks from the present back into the past.

        Time boundary is anchored at today: ongoing overlaps (overlap_end =
        _MAX_DATE) are treated as ending today, preventing the sentinel from
        propagating as an unbounded T through every subsequent hop.

        Returns:
            (path, chosen_overlaps) where path is a list of person node IDs
            and chosen_overlaps is a parallel list of overlap dicts used on
            each edge, or (None, None) when no valid path exists.
        """
        if source == target:
            return [source], []

        today = date_type.today()

        # Queue items: (current_node, time_boundary, path, overlaps_used)
        # Start at today — the most recent point in the backwards search.
        queue: deque = deque([(source, today, [source], [])])
        # visited: node → latest time_boundary at which it was enqueued.
        # Only re-enqueue if we can reach the node at a strictly later
        # boundary (more future options for downstream hops).
        visited: dict = {source: today}

        while queue:
            current, T, path, ovs = queue.popleft()

            for neighbor in G.neighbors(current):
                edge = G.edges[current, neighbor]

                # Cap ongoing overlaps at today so the sentinel value
                # (_MAX_DATE) never passes through as the new boundary.
                best_ov = None
                best_eff: date_type | None = None
                for ov in edge.get("overlaps", []):
                    eff = min(ov["overlap_end"], today)
                    if eff <= T and (best_eff is None or eff > best_eff):
                        best_ov = ov
                        best_eff = eff

                if best_ov is None:
                    continue  # no valid backwards edge to this neighbour

                new_path = path + [neighbor]
                new_ovs = ovs + [best_ov]

                if neighbor == target:
                    return new_path, new_ovs

                prev_T = visited.get(neighbor)
                # Only enqueue if we can arrive with a later (better)
                # time boundary than any previous visit.
                if prev_T is None or best_eff > prev_T:
                    visited[neighbor] = best_eff
                    queue.append(
                        (neighbor, best_eff, new_path, new_ovs)
                    )

        return None, None

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
        # Step 4: Find the shortest backwards-temporal path among all pairs
        shortest_person_path_ids = None
        shortest_chosen_overlaps = None

        for source_node in valid_source_nodes:
            for target_node in valid_target_nodes:
                if source_node == target_node:
                    if shortest_person_path_ids is None:
                        shortest_person_path_ids = [source_node]
                        shortest_chosen_overlaps = []
                    continue
                path, chosen_ovs = self._bfs_backwards_temporal(
                    colleague_G, source_node, target_node
                )
                if path is not None and (
                    shortest_person_path_ids is None
                    or len(path) < len(shortest_person_path_ids)
                ):
                    shortest_person_path_ids = path
                    shortest_chosen_overlaps = chosen_ovs

        # Step 5: If a path was found, convert IDs to names
        if not shortest_person_path_ids:
            self.logger.info(
                f"No valid temporal path found between any of "
                f"{valid_source_nodes} and any of {valid_target_nodes}."
            )
            return []

        # Step 6: Build a structured representation of the full path,
        #         weaving in the connecting org at each hop.
        structured_path = []

        def get_int_id(prefixed_id):
            return int(prefixed_id.split("_")[1])

        # Add the first person
        first_person_id = get_int_id(shortest_person_path_ids[0])
        structured_path.append({"type": "person", "id": first_person_id})

        # Weave org nodes between consecutive people using the overlap
        # that was actually chosen by the backwards-temporal BFS.
        if len(shortest_person_path_ids) > 1:
            for i in range(len(shortest_person_path_ids) - 1):
                chosen_ov = (shortest_chosen_overlaps or [])[i] if (
                    shortest_chosen_overlaps
                ) else None
                if chosen_ov:
                    connecting_org_id = chosen_ov["org_id"]
                else:
                    # Fallback: use first overlap on edge
                    edge_data = colleague_G.edges[
                        shortest_person_path_ids[i],
                        shortest_person_path_ids[i + 1],
                    ]
                    connecting_org_id = edge_data["overlaps"][0]["org_id"]

                p2_id = get_int_id(shortest_person_path_ids[i + 1])
                structured_path.append(
                    {"type": "org", "id": connecting_org_id}
                )
                structured_path.append({"type": "person", "id": p2_id})

        # Step 5: Format the output as prefixed node IDs or plain names
        final_path = []
        for item in structured_path:
            if item["type"] == "person":
                node_id = f"person_{item['id']}"
                final_path.append(
                    node_id if ids_only
                    else colleague_G.nodes[node_id]["name"]
                )
            else:  # type is 'org'
                node_id = f"org_{item['id']}"
                final_path.append(
                    node_id if ids_only
                    else full_G.nodes[node_id]["name"]
                )

        return final_path

    async def find_shortest_nontemporal_path(
        self,
        person1_ids: Union[int, List[int]],
        person2_ids: Union[int, List[int]],
        ids_only: bool = False,
    ) -> List[str]:
        """
        Finds the shortest colleague path with no temporal ordering
        constraint, using the same colleague graph as the temporal search.

        The output is an alternating person → org → person sequence
        (identical structure to find_shortest_temporal_path) so the
        frontend can render both modes identically.  For each hop the
        connecting org is the one whose overlap ended most recently.
        """
        colleague_G = await self._build_colleague_graph()
        full_G = await self.build_full_history_graph()

        source_ids_int = (
            [person1_ids] if isinstance(person1_ids, int) else person1_ids
        )
        target_ids_int = (
            [person2_ids] if isinstance(person2_ids, int) else person2_ids
        )
        source_nodes = [f"person_{pid}" for pid in source_ids_int]
        target_nodes = [f"person_{pid}" for pid in target_ids_int]

        valid_source_nodes = [
            n for n in source_nodes if n in colleague_G
        ]
        valid_target_nodes = [
            n for n in target_nodes if n in colleague_G
        ]

        if not valid_source_nodes or not valid_target_nodes:
            self.logger.warning(
                f"No valid source or target IDs found in the colleague "
                f"graph. Sources given: {source_ids_int}, Targets given: "
                f"{target_ids_int}"
            )
            return []

        shortest_person_path_ids = None

        for source_node in valid_source_nodes:
            for target_node in valid_target_nodes:
                if source_node == target_node:
                    if shortest_person_path_ids is None:
                        shortest_person_path_ids = [source_node]
                    continue
                try:
                    path = nx.shortest_path(
                        colleague_G,
                        source=source_node,
                        target=target_node,
                    )
                    if shortest_person_path_ids is None or len(
                        path
                    ) < len(shortest_person_path_ids):
                        shortest_person_path_ids = path
                except nx.NetworkXNoPath:
                    continue
                except Exception as e:
                    self.logger.error(
                        f"Error finding non-temporal path "
                        f"({source_node}, {target_node}): {e}"
                    )
                    continue

        if not shortest_person_path_ids:
            self.logger.info(
                f"No non-temporal path found between any of "
                f"{valid_source_nodes} and any of {valid_target_nodes}."
            )
            return []

        def get_int_id(prefixed_id: str) -> int:
            return int(prefixed_id.split("_")[1])

        structured_path = []
        structured_path.append(
            {"type": "person", "id": get_int_id(shortest_person_path_ids[0])}
        )

        if len(shortest_person_path_ids) > 1:
            today = date_type.today()
            for i in range(len(shortest_person_path_ids) - 1):
                edge_data = colleague_G.edges[
                    shortest_person_path_ids[i],
                    shortest_person_path_ids[i + 1],
                ]
                # Pick the most-recent overlap as the connecting org
                overlaps = edge_data.get("overlaps", [])
                best = max(
                    overlaps,
                    key=lambda ov: min(ov["overlap_end"], today),
                    default=None,
                )
                connecting_org_id = (
                    best["org_id"] if best else overlaps[0]["org_id"]
                )
                p2_id = get_int_id(shortest_person_path_ids[i + 1])
                structured_path.append(
                    {"type": "org", "id": connecting_org_id}
                )
                structured_path.append({"type": "person", "id": p2_id})

        final_path = []
        for item in structured_path:
            if item["type"] == "person":
                node_id = f"person_{item['id']}"
                final_path.append(
                    node_id if ids_only
                    else colleague_G.nodes[node_id]["name"]
                )
            else:
                node_id = f"org_{item['id']}"
                final_path.append(
                    node_id if ids_only
                    else full_G.nodes[node_id]["name"]
                )

        return final_path

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

    async def get_connected_entities(
        self,
        person_ids: Union[int, List[int]],
        max_degree: int = 1,
        include_organizations: bool = True,
        include_people: bool = True,
    ) -> Dict[str, Any]:
        """
        Extract names and organizations connected to a person within a specified
        degree of connectivity.

        Args:
            person_ids: Single person ID or list of IDs (treated as same person)
            max_degree: Maximum degree of separation (1 = direct connections only)
            target_date: Optional date for snapshot-based analysis
            include_organizations: Whether to include organizations in results
            include_people: Whether to include people in results

        Returns:
            Dictionary containing connected entities organized by degree and type
        """
        try:
            # Normalize input to list
            person_ids_list = (
                [person_ids] if isinstance(person_ids, int) else person_ids
            )

            # Use full history graph for comprehensive connectivity
            G = await self.build_full_history_graph()

            # Check which person nodes exist in the graph
            person_nodes = [f"person_{pid}" for pid in person_ids_list]
            valid_person_nodes = [
                node for node in person_nodes if node in G
            ]

            if not valid_person_nodes:
                self.logger.warning(
                    f"None of the person IDs {person_ids_list} found in graph"
                )
                return {
                    "error": f"None of the person IDs {person_ids_list} found"
                }

            # Get names for all valid person nodes (for display)
            source_persons = []
            for node in valid_person_nodes:
                person_id_int = int(node.split("_")[1])
                source_persons.append(
                    {"id": person_id_int, "name": G.nodes[node]["name"]}
                )

            # Convert to undirected for connectivity analysis
            undirected_G = G.to_undirected()

            # Initialize result structure
            result = {
                "source_persons": source_persons,
                "connections_by_degree": {},
                "summary": {
                    "total_people": 0,
                    "total_organizations": 0,
                    "max_degree_searched": max_degree,
                    "source_person_count": len(valid_person_nodes),
                },
            }

            # Track visited nodes to avoid duplicates (include all source persons)
            visited = set(valid_person_nodes)
            current_level = set(valid_person_nodes)

            # BFS to find connections at each degree
            for degree in range(1, max_degree + 1):
                next_level = set()
                degree_connections = {"people": [], "organizations": []}

                # Find all neighbors of current level nodes
                for node in current_level:
                    for neighbor in undirected_G.neighbors(node):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            next_level.add(neighbor)

                            # Get node information
                            node_data = G.nodes[neighbor]
                            node_type = node_data.get("type")

                            if node_type == "person" and include_people:
                                # Extract person ID from prefixed format
                                person_id_int = int(neighbor.split("_")[1])
                                degree_connections["people"].append(
                                    {
                                        "id": person_id_int,
                                        "name": node_data["name"],
                                    }
                                )
                            elif (
                                node_type == "organization"
                                and include_organizations
                            ):
                                # Extract org ID from prefixed format
                                org_id_int = int(neighbor.split("_")[1])
                                degree_connections["organizations"].append(
                                    {
                                        "id": org_id_int,
                                        "name": node_data["name"],
                                    }
                                )

                # Only add degree if there are connections
                if (
                    degree_connections["people"]
                    or degree_connections["organizations"]
                ):
                    result["connections_by_degree"][degree] = (
                        degree_connections
                    )

                # Update current level for next iteration
                current_level = next_level

                # Break if no more connections found
                if not current_level:
                    break

            # Calculate summary statistics
            for degree_data in result["connections_by_degree"].values():
                result["summary"]["total_people"] += len(
                    degree_data["people"]
                )
                result["summary"]["total_organizations"] += len(
                    degree_data["organizations"]
                )

            self.logger.info(
                f"Found {result['summary']['total_people']} people and "
                f"{result['summary']['total_organizations']} organizations "
                f"within {max_degree} degrees of person(s) {person_ids_list}"
            )

            return result

        except Exception as e:
            self.logger.error(
                f"Error getting connected entities for person(s) {person_ids}: {e}"
            )
            raise

    async def get_colleague_network(
        self,
        person_ids: Union[int, List[int]],
        max_degree: int = 2,
    ) -> Dict[str, Any]:
        """
        Get the colleague network for a person using the temporal colleague graph.
        This shows only people who were actual colleagues (overlapping employment).

        Args:
            person_ids: Single person ID or list of IDs (treated as same person)
            max_degree: Maximum degree of separation through colleague relationships

        Returns:
            Dictionary containing colleague network organized by degree
        """
        try:
            # Normalize input to list
            person_ids_list = (
                [person_ids] if isinstance(person_ids, int) else person_ids
            )

            # Use the colleague-specific graph
            colleague_G = await self._build_colleague_graph()

            # Check which person nodes exist in the colleague graph
            person_nodes = [f"person_{pid}" for pid in person_ids_list]
            valid_person_nodes = [
                node for node in person_nodes if node in colleague_G
            ]

            if not valid_person_nodes:
                self.logger.warning(
                    f"None of the person IDs {person_ids_list} found in colleague graph"
                )
                return {
                    "error": f"None of the person IDs {person_ids_list} found in colleague network"
                }

            # Get names for all valid person nodes (for display)
            source_persons = []
            for node in valid_person_nodes:
                person_id_int = int(node.split("_")[1])
                source_persons.append(
                    {
                        "id": person_id_int,
                        "name": colleague_G.nodes[node]["name"],
                    }
                )

            # Initialize result structure
            result = {
                "source_persons": source_persons,
                "colleagues_by_degree": {},
                "summary": {
                    "total_colleagues": 0,
                    "max_degree_searched": max_degree,
                    "source_person_count": len(valid_person_nodes),
                },
            }

            # Track visited nodes and current level (include all source persons)
            visited = set(valid_person_nodes)
            current_level = set(valid_person_nodes)

            # BFS through colleague network
            for degree in range(1, max_degree + 1):
                next_level = set()
                degree_colleagues = []

                for node in current_level:
                    for neighbor in colleague_G.neighbors(node):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            next_level.add(neighbor)

                            # Get colleague information
                            colleague_id_int = int(neighbor.split("_")[1])
                            colleague_name = colleague_G.nodes[neighbor][
                                "name"
                            ]

                            # Get shared organizations with the connecting node
                            edge_data = colleague_G.edges[node, neighbor]
                            shared_orgs = [
                                ov["org_id"]
                                for ov in edge_data.get("overlaps", [])
                            ]

                            # Determine connection path
                            connection_through = "direct"
                            if node not in valid_person_nodes:
                                # This neighbor is connected through an intermediate person
                                connection_through = int(node.split("_")[1])

                            degree_colleagues.append(
                                {
                                    "id": colleague_id_int,
                                    "name": colleague_name,
                                    "shared_organizations": shared_orgs,
                                    "connection_through": connection_through,
                                }
                            )

                # Add degree data if colleagues found
                if degree_colleagues:
                    result["colleagues_by_degree"][degree] = (
                        degree_colleagues
                    )
                    result["summary"]["total_colleagues"] += len(
                        degree_colleagues
                    )

                # Update for next iteration
                current_level = next_level

                # Break if no more connections
                if not current_level:
                    break

            self.logger.info(
                f"Found {result['summary']['total_colleagues']} colleagues "
                f"within {max_degree} degrees of person(s) {person_ids_list}"
            )

            return result

        except Exception as e:
            self.logger.error(
                f"Error getting colleague network for person(s) {person_ids}: {e}"
            )
            raise
