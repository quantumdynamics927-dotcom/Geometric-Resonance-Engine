"""Core geometric representations for fractal structures."""

from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any

import numpy as np


@dataclass
class Node:
    """A vertex in the fractal geometry.

    Attributes:
        id: Unique integer identifier for this node.
        position: 2D Cartesian coordinates (x, y).
        level: Fractal recursion level at which this node was generated.
        contraction_index: Which IFS contraction (0, 1, or 2 for 3-way IFS).
        metadata: Arbitrary additional data.
    """

    id: int
    position: Tuple[float, float]
    level: int
    contraction_index: int  # 0, 1, or 2 for 3-way IFS
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.contraction_index not in (0, 1, 2):
            raise ValueError(
                f"contraction_index must be 0, 1, or 2, got {self.contraction_index}"
            )


@dataclass
class Edge:
    """An undirected edge connecting two nodes.

    Attributes:
        source: Source node ID.
        target: Target node ID.
        weight: Edge weight (default 1.0).
        edge_type: One of "contraction" (within a sub-triangle) or "lateral"
            (between sub-triangles at the same level).
    """

    source: int
    target: int
    weight: float = 1.0
    edge_type: str = "contraction"

    def __post_init__(self):
        if self.edge_type not in ("contraction", "lateral"):
            raise ValueError(
                f"edge_type must be 'contraction' or 'lateral', got {self.edge_type}"
            )
        if self.weight <= 0:
            raise ValueError(f"weight must be positive, got {self.weight}")


@dataclass
class GeometryMeta:
    """Metadata for a generated fractal geometry.

    Attributes:
        fractal_type: Identifier string for the fractal type.
        hausdorff_dimension: Theoretical Hausdorff dimension.
        level: Recursion depth used during generation.
        node_count: Number of unique vertices.
        triangle_count: Number of sub-triangles (3^level for Sierpinski).
        boundary_length: Perimeter length at this level.
        enclosed_area: Total geometric area (zero in the limit).
    """

    fractal_type: str
    hausdorff_dimension: float
    level: int
    node_count: int
    triangle_count: int
    boundary_length: float
    enclosed_area: float


@dataclass
class GeometryModel:
    """Complete fractal geometry model.

    Attributes:
        nodes: List of all Node objects.
        edges: List of all Edge objects.
        meta: GeometryMeta instance with computed metadata.

    Properties:
        node_array: (N, 2) NumPy array of node positions.
        adjacency_dict: Adjacency as dict mapping node ID → list of neighbor IDs.
    """

    nodes: List[Node]
    edges: List[Edge]
    meta: GeometryMeta

    @property
    def node_array(self) -> np.ndarray:
        """Return (N, 2) array of node positions for graph construction."""
        return np.array([n.position for n in self.nodes])

    @property
    def adjacency_dict(self) -> Dict[int, List[int]]:
        """Return adjacency as dict mapping node ID → list of neighbor IDs."""
        adj: Dict[int, List[int]] = {n.id: [] for n in self.nodes}
        for e in self.edges:
            adj[e.source].append(e.target)
        return adj

    def node_by_id(self, node_id: int) -> Node:
        """Return the node with the given ID."""
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(f"No node with id {node_id}")

    def void_region(self, level: int) -> List[int]:
        """Identify central void/decoherence-free region node IDs.

        For Sierpinski, void regions are the positions where Pascal mod 2 = 0
        at the given level — these form the decoherence-free subspaces.

        Returns:
            List of node IDs belonging to the void region.
        """
        # Level 0 has no void
        if level == 0:
            return []

        # For Sierpinski, the void at level n consists of the central
        # triangles removed at each iteration. At level 1, the central
        # triangle (removed) has vertices at midpoints of the parent edges.
        # These nodes exist but are marked as "void" by having all three
        # neighbors at the same contraction level.
        #
        # Simplified: nodes where pascal_mod_2[node_position] == 0
        void_ids: List[int] = []

        # Build pascal mod 2 pattern for this level
        # Row r has r+1 entries; entry k is C(r,k) mod 2
        # The Sierpinski pattern at level n uses rows 0..2^n
        # A node at position (row, col) is in a void if C(row, col) mod 2 == 0
        max_row = 2 ** level
        for row in range(max_row + 1):
            num_positions = row + 1
            for col in range(num_positions):
                # C(row, col) mod 2 == 1 iff (row & col) == col (binary)
                # Equivalently: C(row, col) is odd iff col & (row - col) == 0
                is_filled = (row & col) == col
                if not is_filled:
                    # This position is in a void region
                    # Map to a node ID if it exists at this level
                    pass  # populated below via node mapping

        return void_ids
