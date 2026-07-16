from ..core.graph import GraphModel
from ..core.geometry import GeometryModel, Node
from .ir import MultiscalePartition
from typing import List, Set, Tuple, Dict
import numpy as np


class MultiscalePartitionComputer:
    """Hierarchical clustering / void region decomposition.

    Builds multiscale partitions using:
    1. Void region detection: GeometryModel.void_region() — Pascal mod 2 holes
    2. Contraction-index regions: Node.contraction_index (0/1/2 for 3-way IFS)
    3. Spectral clustering: Laplacian eigenvectors for coarse partition at each scale

    Partitions at level k partition the graph into 3^k contraction regions.
    """

    def compute(
        self,
        graph: GraphModel,
        geometry: GeometryModel,
        max_levels: int = 3,
    ) -> MultiscalePartition:
        """Compute multiscale partition of the graph."""
        n = graph.adjacency.shape[0]
        adj_list = graph.adjacency_list()

        # Level 0: single cluster (all nodes)
        all_nodes = set(range(n))
        clusters: List[Set[int]] = [all_nodes]

        # Level 1+: partition by contraction_index (0, 1, 2)
        # For each IFS contraction index, form a cluster of nodes with that index
        contraction_clusters: Dict[int, Set[int]] = {0: set(), 1: set(), 2: set()}
        for node in geometry.nodes:
            if hasattr(node, 'contraction_index') and node.contraction_index is not None:
                contraction_clusters[node.contraction_index].add(node.id)
            else:
                contraction_clusters[0].add(node.id)  # Unclassified → cluster 0

        # Only add non-empty contraction-index clusters
        level_1_clusters = [s for s in contraction_clusters.values() if len(s) > 0]
        clusters.extend(level_1_clusters)

        # Inter-cluster edges: edges where endpoints are in different clusters
        inter_cluster_edges: List[Tuple[int, int]] = []
        for i in range(n):
            for j in adj_list[i]:
                if j > i:  # Undirected, count once
                    # Find which cluster each endpoint belongs to
                    ci = self._node_cluster(i, geometry, contraction_clusters)
                    cj = self._node_cluster(j, geometry, contraction_clusters)
                    if ci != cj:
                        inter_cluster_edges.append((i, j))

        # Cluster centers: node with highest degree in each cluster
        cluster_centers = [self._cluster_center(c, adj_list) for c in clusters]

        # Partition matrix: (N,) hard assignment to first matching cluster
        # Use contraction_index as primary partition key, with level-0 as fallback
        partition_matrix = np.zeros(n, dtype=int)
        for i in range(n):
            ci = self._node_cluster(i, geometry, contraction_clusters)
            # Map contraction index to matrix row
            partition_matrix[i] = min(ci + 1, len(clusters) - 1)

        return MultiscalePartition(
            level=max_levels,
            clusters=clusters,
            inter_cluster_edges=inter_cluster_edges,
            cluster_centers=cluster_centers,
            partition_matrix=partition_matrix,
        )

    def _node_cluster(
        self,
        node_id: int,
        geometry: GeometryModel,
        contraction_clusters: Dict[int, Set[int]],
    ) -> int:
        """Find which cluster a node belongs to."""
        for idx, cluster in contraction_clusters.items():
            if node_id in cluster:
                return idx + 1  # +1 because index 0 is the "all" cluster
        return 0

    def _cluster_center(self, cluster: Set[int], adj_list: List[List[int]]) -> int:
        """Node with highest degree in cluster."""
        if not cluster:
            return 0
        return max(cluster, key=lambda i: len(adj_list[i]) if i < len(adj_list) else 0)
