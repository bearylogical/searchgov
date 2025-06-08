import networkx as nx
from typing import List, Dict, Any, Optional
from src.services.query import QueryService
import logging
from datetime import datetime


class GraphService:
    def __init__(self, query_service: QueryService):
        self.query_service = query_service
        self.logger = logging.getLogger(__name__)
        self._graph_cache = None
        self._cache_date = None

    def build_networkx_graph(
        self, target_date: str = None
    ) -> nx.MultiDiGraph:
        """Build NetworkX graph for advanced algorithms"""
        if target_date is None:
            target_date = datetime.now().strftime("%Y-%m-%d")

        # Use cache if available and date matches
        if self._graph_cache and self._cache_date == target_date:
            return self._graph_cache

        try:
            snapshot = self.query_service.get_network_snapshot(target_date)

            G = nx.MultiDiGraph()

            for record in snapshot:
                # Add person node
                G.add_node(
                    record["person_name"],
                    type="person",
                    tel=record.get("tel"),
                    email=record.get("email"),
                )

                # Add organization node
                G.add_node(record["org_name"], type="organization")

                # Add employment edge
                G.add_edge(
                    record["person_name"],
                    record["org_name"],
                    relationship="employed_at",
                    rank=record["rank"],
                    start_date=record["start_date"],
                    end_date=record["end_date"],
                )

            # Cache the result
            self._graph_cache = G
            self._cache_date = target_date

            return G

        except Exception as e:
            self.logger.error(f"Error building NetworkX graph: {e}")
            return nx.MultiDiGraph()

    def find_shortest_path(
        self, person1: str, person2: str, target_date: str = None
    ) -> List[str]:
        """Find shortest path between two people"""
        G = self.build_networkx_graph(target_date)

        try:
            return nx.shortest_path(
                G.to_undirected(), source=person1, target=person2
            )
        except nx.NetworkXNoPath:
            return []
        except Exception as e:
            self.logger.error(f"Error finding shortest path: {e}")
            return []

    def calculate_centrality_metrics(
        self, target_date: str = None
    ) -> Dict[str, Dict]:
        """Calculate centrality metrics"""
        G = self.build_networkx_graph(target_date)

        # Create person-only graph
        person_graph = nx.Graph()
        for person1 in G.nodes():
            if G.nodes[person1].get("type") == "person":
                for org in G.neighbors(person1):
                    if G.nodes[org].get("type") == "organization":
                        for person2 in G.neighbors(org):
                            if (
                                G.nodes[person2].get("type") == "person"
                                and person1 != person2
                            ):
                                person_graph.add_edge(person1, person2)

        try:
            return {
                "betweenness_centrality": dict(
                    nx.betweenness_centrality(person_graph)
                ),
                "degree_centrality": dict(
                    nx.degree_centrality(person_graph)
                ),
                "closeness_centrality": dict(
                    nx.closeness_centrality(person_graph)
                ),
            }
        except Exception as e:
            self.logger.error(f"Error calculating centrality: {e}")
            return {}
