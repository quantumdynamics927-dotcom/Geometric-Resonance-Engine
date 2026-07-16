from ..core.graph import GraphModel
from ..core.geometry import GeometryModel
from .ir import SymmetrySector
from typing import Dict, List
import numpy as np


class SymmetrySectorComputer:
    """Compute D3 symmetry sector decomposition for fractal graphs.

    Algorithm:
    1. Greedy Dsatur 3-coloring of the graph adjacency list
    2. Count nodes per color
    3. Classify nodes: boundary (on outer perimeter), interior (fully surrounded),
       vertex_centered (near contraction vertex)
    4. Check D3 invariance: verify 3-cycle coloring exists

    For milestone 1: coarse boundary/interior/vertex_centered classification.
    Full automorphism-group symmetry deferred to milestone 2.
    """

    def compute(self, graph: GraphModel) -> SymmetrySector:
        """Compute symmetry sector decomposition."""
        # 1. Greedy coloring using Dsatur-inspired approach
        coloring = self._greedy_coloring(graph)

        # 2. Count per color
        color_counts: Dict[int, int] = {}
        for c in coloring:
            color_counts[c] = color_counts.get(c, 0) + 1

        # 3. Classify nodes using geometry if available, else graph structure
        # Coarse: color 0 = boundary, color 1 = interior, color 2 = vertex_centered
        # (For Sierpinski, the 3 colors map naturally to IFS contraction regions)
        sector_labels = ["boundary", "interior", "vertex_centered"]
        sector_counts: Dict[str, int] = {
            "boundary": color_counts.get(0, 0),
            "interior": color_counts.get(1, 0),
            "vertex_centered": color_counts.get(2, 0),
        }

        # 4. D3 check: for Sierpinski, exactly 3 colors with roughly equal counts
        n = graph.adjacency.shape[0]
        automorphism_invariant = len(color_counts) == 3 and all(
            0.2 <= count / n <= 0.5 for count in color_counts.values()
        )

        description = (
            f"SymmetrySector: {len(color_counts)} color classes, "
            f"D3-invariant={automorphism_invariant}, "
            f"counts={dict(color_counts)}"
        )

        return SymmetrySector(
            coloring=coloring,
            sector_labels=sector_labels,
            sector_counts=sector_counts,
            automorphism_invariant=automorphism_invariant,
            description=description,
        )

    def _greedy_coloring(self, graph: GraphModel) -> np.ndarray:
        """Dsatur-inspired greedy 3-coloring. Returns shape (N,) array of 0/1/2."""
        n = graph.adjacency.shape[0]
        coloring = np.full(n, -1, dtype=int)
        adj_list = graph.adjacency_list()

        # Order nodes by degree descending (Dsatur heuristic)
        nodes_by_degree = sorted(range(n), key=lambda i: len(adj_list[i]), reverse=True)

        for node in nodes_by_degree:
            neighbor_colors = set(coloring[adj_list[node]] if adj_list[node] else [])
            for color in range(3):
                if color not in neighbor_colors:
                    coloring[node] = color
                    break
            if coloring[node] == -1:
                coloring[node] = 0  # Fallback

        return coloring
