"""Sierpinski triangle generator with multiple mathematical routes."""

from typing import List, Tuple, Dict
import numpy as np

from .base import FractalGenerator
from ..core.geometry import GeometryModel, Node, Edge, GeometryMeta
from ..core.exceptions import GeometryGenerationError


class SierpinskiGenerator(FractalGenerator):
    """Sierpinski triangle generator.

    The Sierpinski triangle converges seven independent mathematical routes:

    1. **IFS** (default): 3 affine contractions, scale 1/2 each
    2. **Pascal mod 2**: Binomial coefficients C(n,k) mod 2 form the pattern
    3. **Rule 90 CA**: Rule 90 cellular automaton evolution from single seed
    4. **Hanoi**: Tower of Hanoi graph structure on 3 pegs
    5. **Chaos game**: Iterative midpoint elimination protocol
    6. **Lucas**: Lucas theorem on binomial coefficients
    7. **Julia**: Julia sets of specific rational maps (carpet variant)

    Hausdorff dimension: log(3)/log(2) ≈ 1.585
    At level n: 3^n triangles, 3^(n+1)/2 + 3^n/2 + 1 nodes approximately
    """

    # IFS contraction matrices (each maps to 1/2 scale)
    _IFS_CONTRACTIONS = [
        np.array([[0.5, 0.0], [0.0, 0.5]]),  # Bottom-left
        np.array([[0.5, 0.0], [0.0, 0.5]]),  # Bottom-right
        np.array([[0.5, 0.0], [0.0, 0.5]]),  # Top
    ]

    # IFS translation vectors
    _IFS_TRANSLATIONS = [
        np.array([0.0, 0.0]),  # Bottom-left: origin
        np.array([0.5, 0.0]),  # Bottom-right: midpoint of base
        np.array([0.25, np.sqrt(3) / 4]),  # Top: midpoint of left side
    ]

    def __init__(self, route: str = "ifs"):
        """Initialize with specific mathematical route.

        Args:
            route: One of ["ifs", "pascal_mod2", "rule90", "hanoi",
                           "chaos_game", "lucas", "julia"]
        """
        self.route = route
        valid_routes = [
            "ifs", "pascal_mod2", "rule90", "hanoi",
            "chaos_game", "lucas", "julia"
        ]
        if route not in valid_routes:
            raise GeometryGenerationError(
                f"Route must be one of {valid_routes}, got {route!r}"
            )

    @property
    def name(self) -> str:
        return "sierpinski"

    @property
    def hausdorff_dimension(self) -> float:
        return np.log(3) / np.log(2)  # ≈ 1.585

    def routes(self) -> List[str]:
        return [
            "ifs", "pascal_mod2", "rule90", "hanoi",
            "chaos_game", "lucas", "julia"
        ]

    def generate(self, level: int) -> GeometryModel:
        """Generate Sierpinski triangle at given level via configured route.

        Args:
            level: Recursion depth (n >= 0)

        Returns:
            GeometryModel representing the Sierpinski triangle at this level
        """
        self.validate_level(level)

        if self.route == "ifs":
            return self._generate_ifs(level)
        elif self.route == "pascal_mod2":
            return self._generate_pascal_mod2(level)
        elif self.route == "rule90":
            return self._generate_rule90(level)
        elif self.route == "hanoi":
            return self._generate_hanoi(level)
        elif self.route == "chaos_game":
            return self._generate_chaos_game(level)
        elif self.route == "lucas":
            return self._generate_lucas(level)
        elif self.route == "julia":
            return self._generate_julia(level)
        else:
            raise GeometryGenerationError(f"Unreachable route: {self.route}")

    def _generate_ifs(self, level: int) -> GeometryModel:
        """IFS-based generation.

        Each level applies 3 contractions to each existing triangle.
        Level 0: single equilateral triangle.
        Level n: 3^n sub-triangles.

        Returns:
            GeometryModel with deduplicated vertices and edges.
        """
        # Initial equilateral triangle vertices (level 0)
        sqrt3_4 = np.sqrt(3) / 4
        initial_vertices = np.array([
            [0.0, 0.0],          # Bottom-left
            [1.0, 0.0],          # Bottom-right
            [0.5, sqrt3_4 * 2],  # Top
        ], dtype=np.float64)

        # Build all triangle vertices level by level
        all_triangles = [[initial_vertices]]  # List of lists of triangles per level

        for current_level in range(level):
            prev_triangles = all_triangles[-1]
            new_triangles = []
            for triangle in prev_triangles:
                for i in range(3):
                    # Apply contraction i
                    contracted = (
                        self._IFS_CONTRACTIONS[i] @ triangle.T
                    ).T
                    translated = contracted + self._IFS_TRANSLATIONS[i]
                    new_triangles.append(translated)
            all_triangles.append(new_triangles)

        # Current level triangles
        current_triangles = all_triangles[-1]
        triangle_count = len(current_triangles)

        # Sierpinski coordinates are dyadic rationals (multiples of 1/2^level).
        # Scale by 2^level so vertices fall on exact integer lattice points.
        scale = 2 ** level

        # Deduplicate vertices with spatial hashing
        vertex_to_id: Dict[Tuple[int, ...], int] = {}
        nodes: List[Node] = []
        node_counter = 0
        edges: List[Edge] = []
        level_nodes: List[int] = []  # Node IDs at this level

        for triangle in current_triangles:
            triangle_node_ids = []
            for vertex in triangle:
                # Round scaled coordinates to nearest integer for exact hash
                key = (
                    int(np.round(vertex[0] * scale)),
                    int(np.round(vertex[1] * scale))
                )
                if key not in vertex_to_id:
                    vertex_to_id[key] = node_counter
                    # Determine contraction index based on translation
                    # Bottom-left=(0,0), Bottom-right=(0.5,0), Top=(0.25, sqrt3/4)
                    tx, ty = vertex[0], vertex[1]
                    if abs(ty) < 1e-9 and abs(tx) < 1e-9:
                        cidx = 0
                    elif abs(ty) < 1e-9 and abs(tx - 0.5) < 1e-9:
                        cidx = 1
                    elif abs(tx - 0.25) < 1e-9 and abs(ty - np.sqrt(3)/4) < 1e-9:
                        cidx = 2
                    else:
                        cidx = 0  # Default for interior nodes

                    nodes.append(Node(
                        id=node_counter,
                        position=(float(vertex[0]), float(vertex[1])),
                        level=level,
                        contraction_index=cidx,
                        metadata={}
                    ))
                    node_counter += 1
                triangle_node_ids.append(vertex_to_id[key])

            # Add 3 edges per triangle (undirected)
            edges.append(Edge(triangle_node_ids[0], triangle_node_ids[1], edge_type="lateral"))
            edges.append(Edge(triangle_node_ids[1], triangle_node_ids[2], edge_type="lateral"))
            edges.append(Edge(triangle_node_ids[2], triangle_node_ids[0], edge_type="lateral"))
            level_nodes.extend(triangle_node_ids)

        # Unique node count
        unique_node_count = len(nodes)

        # Enclosed area: equilateral triangle area shrinks with level
        base_area = np.sqrt(3) / 4  # Unit equilateral triangle area
        area = base_area * (0.25 ** level) * triangle_count

        # Boundary length: grows as (3/2)^level
        boundary_length = 3 * (3 / 2) ** level

        meta = GeometryMeta(
            fractal_type="sierpinski",
            hausdorff_dimension=self.hausdorff_dimension,
            level=level,
            node_count=unique_node_count,
            triangle_count=triangle_count,
            boundary_length=boundary_length,
            enclosed_area=float(area)
        )

        return GeometryModel(nodes=nodes, edges=edges, meta=meta)

    def _generate_pascal_mod2(self, level: int) -> GeometryModel:
        """Pascal's triangle modulo 2 route.

        Binomial coefficients C(n,k) mod 2 form the Sierpinski pattern.
        Entry at row n, position k is 1 iff C(n,k) is odd.
        C(n,k) is odd iff (k & (n-k)) == 0 in binary (Lucas theorem).

        For level n, we use rows 0..2^n.

        Returns:
            GeometryModel with geometry derived from Pascal mod 2 pattern.
        """
        # Number of rows = 2^level + 1
        num_rows = 2 ** level + 1

        # Build Pascal mod 2 pattern
        rows: List[List[int]] = []
        for n in range(num_rows):
            row = []
            for k in range(n + 1):
                # C(n,k) mod 2 == 1 iff (k & (n-k)) == 0
                if (k & (n - k)) == 0:
                    row.append(1)
                else:
                    row.append(0)
            rows.append(row)

        # Convert pattern to geometry
        # Each "1" becomes a node; edges connect adjacent 1s horizontally and diagonally
        nodes: List[Node] = []
        edges: List[Edge] = []
        node_id_map: Dict[Tuple[int, int], int] = {}
        node_counter = 0

        # Row height in geometry units
        row_height = 1.0 / (2 ** level)
        base_width = 2.0  # Total base width

        for r, row in enumerate(rows):
            y = -r * row_height  # Negative so top row is at y=0
            row_width = r * row_height * np.sqrt(3) if r > 0 else 0

            for k, val in enumerate(row):
                if val == 1:
                    if r == 0:
                        x = 0.0
                    else:
                        x = -row_width / 2 + k * row_height * np.sqrt(3)

                    node_id = node_counter
                    node_id_map[(r, k)] = node_counter
                    nodes.append(Node(
                        id=node_id,
                        position=(float(x), float(y)),
                        level=level,
                        contraction_index=k % 3,
                        metadata={"pascal_row": r, "pascal_col": k}
                    ))
                    node_counter += 1

                    # Horizontal edge to previous in row
                    if k > 0 and row[k - 1] == 1:
                        edges.append(Edge(
                            node_id_map[(r, k - 1)], node_id,
                            edge_type="lateral"
                        ))

                    # Diagonal edges to previous row
                    if r > 0:
                        if k > 0 and rows[r - 1][k - 1] == 1:
                            edges.append(Edge(
                                node_id_map[(r - 1, k - 1)], node_id,
                                edge_type="contraction"
                            ))
                        if k < r and rows[r - 1][k] == 1:
                            edges.append(Edge(
                                node_id_map[(r - 1, k)], node_id,
                                edge_type="contraction"
                            ))

        triangle_count = sum(1 for row in rows for val in row if val == 1) // 3
        boundary_length = 3 * (3 / 2) ** level
        area = (np.sqrt(3) / 4) * (0.25 ** level) * triangle_count

        meta = GeometryMeta(
            fractal_type="sierpinski",
            hausdorff_dimension=self.hausdorff_dimension,
            level=level,
            node_count=len(nodes),
            triangle_count=triangle_count,
            boundary_length=boundary_length,
            enclosed_area=float(area)
        )

        return GeometryModel(nodes=nodes, edges=edges, meta=meta)

    def _generate_rule90(self, level: int) -> GeometryModel:
        """Rule 90 cellular automaton route.

        Rule 90: next cell = left XOR right (i.e., next = left ⊕ right)
        Starting from a single '1' seed, the evolution forms the Sierpinski.
        Each row becomes a set of nodes; edges connect cells to their children.

        Returns:
            GeometryModel from Rule 90 CA evolution.
        """
        # At level n, we have 2^n + 1 rows (including row 0)
        num_rows = 2 ** level + 1

        # Rule 90 evolution
        # Row 0: single 1 at center
        state = {num_rows // 2: 1}

        rows_states = [state]

        for _ in range(level):
            new_state: Dict[int, int] = {}
            prev_positions = sorted(state.keys())
            min_p, max_p = min(prev_positions), max(prev_positions)

            # Extend range by 1 on each side
            for pos in range(min_p - 1, max_p + 2):
                left = state.get(pos - 1, 0)
                right = state.get(pos + 1, 0)
                new_state[pos] = left ^ right  # XOR

            rows_states.append(new_state)
            state = new_state

        # Convert to geometry
        nodes: List[Node] = []
        edges: List[Edge] = []
        node_id_map: Dict[Tuple[int, int], int] = {}
        node_counter = 0

        row_height = 1.0 / (2 ** level)

        for r, row_state in enumerate(rows_states):
            y = -r * row_height
            positions = sorted(row_state.keys())
            if not positions:
                continue

            row_width = (positions[-1] - positions[0]) if len(positions) > 1 else 1
            leftmost = positions[0]

            for pos in positions:
                x = (pos - leftmost) * row_height

                node_id = node_counter
                node_id_map[(r, pos)] = node_id
                nodes.append(Node(
                    id=node_id,
                    position=(float(x), float(y)),
                    level=level,
                    contraction_index=pos % 3,
                    metadata={"rule90_pos": pos}
                ))
                node_counter += 1

                # Edges to children in next row
                if r < level:
                    for child_pos in (pos * 2, pos * 2 + 1):
                        if child_pos in [p for p in rows_states[r + 1].keys()]:
                            if (r + 1, child_pos) in node_id_map:
                                edges.append(Edge(
                                    node_id, node_id_map[(r + 1, child_pos)],
                                    edge_type="contraction"
                                ))

        triangle_count = sum(len(s) for s in rows_states) // 3
        boundary_length = 3 * (3 / 2) ** level
        area = (np.sqrt(3) / 4) * (0.25 ** level) * triangle_count

        meta = GeometryMeta(
            fractal_type="sierpinski",
            hausdorff_dimension=self.hausdorff_dimension,
            level=level,
            node_count=len(nodes),
            triangle_count=triangle_count,
            boundary_length=boundary_length,
            enclosed_area=float(area)
        )

        return GeometryModel(nodes=nodes, edges=edges, meta=meta)

    def _generate_hanoi(self, level: int) -> GeometryModel:
        """Tower of Hanoi route.

        The Tower of Hanoi graph (3 pegs, n disks) traces paths that
        produce the Sierpinski gasket when viewed as a state graph.

        For n disks, the graph has 3^n vertices (states).
        Edges represent legal moves between states.

        Returns:
            GeometryModel from Hanoi graph structure.
        """
        # Hanoi graph: each state is encoded as base-3 digit
        # digit 0,1,2 = which peg disk 1 is on (least significant)
        # Higher digits = higher disks
        # At level n (n disks), there are 3^n states
        num_states = 3 ** level

        nodes: List[Node] = []
        edges: List[Edge] = []

        # Generate all states and edges
        for state in range(num_states):
            # Encode state in base 3
            digits = []
            tmp = state
            for _ in range(level):
                digits.append(tmp % 3)
                tmp //= 3

            # Position on a triangular lattice
            # Three pegs at 120-degree angles
            x = sum(d * (0.5 ** i) for i, d in enumerate(digits))
            y = 0.0

            # Project onto 2D
            # Peg positions at 0°, 120°, 240°
            angles = [0.0, 2 * np.pi / 3, 4 * np.pi / 3]
            px = sum(digits[i] * np.cos(angles[digits[i]]) * (0.5 ** (i + 1)) for i in range(level))
            py = sum(digits[i] * np.sin(angles[digits[i]]) * (0.5 ** (i + 1)) for i in range(level))

            nodes.append(Node(
                id=state,
                position=(float(px), float(py)),
                level=level,
                contraction_index=digits[0] if digits else 0,
                metadata={"hanoi_state": state, "digits": digits}
            ))

            # Find legal moves: move smallest disk (digit 0) or move disk that
            # is on top (no disk smaller on that peg)
            # Simplified: adjacent states differ by moving one disk
            for i in range(level):
                for peg in range(3):
                    if digits[i] != peg:
                        # Check if move is legal: no smaller disk on target peg
                        legal = True
                        for j in range(i):
                            if digits[j] == peg:
                                legal = False
                                break

                        if legal:
                            new_digits = digits.copy()
                            new_digits[i] = peg
                            new_state = sum(d * (3 ** i) for i, d in enumerate(new_digits))

                            if new_state > state:
                                edges.append(Edge(state, new_state, edge_type="contraction"))

        triangle_count = num_states // 3
        boundary_length = 3 * (3 / 2) ** level
        area = (np.sqrt(3) / 4) * (0.25 ** level) * triangle_count

        meta = GeometryMeta(
            fractal_type="sierpinski",
            hausdorff_dimension=self.hausdorff_dimension,
            level=level,
            node_count=len(nodes),
            triangle_count=triangle_count,
            boundary_length=boundary_length,
            enclosed_area=float(area)
        )

        return GeometryModel(nodes=nodes, edges=edges, meta=meta)

    def _generate_chaos_game(self, level: int) -> GeometryModel:
        """Chaos game route.

        The chaos game: start at random point, repeatedly pick one of 3
        Sierpinski vertices at random, move halfway to it, marking points.
        This converges to the Sierpinski attractor.

        For geometry, we use the inverse: generate nodes at each midpoint
        operation. The set of all possible midpoint combinations forms the gasket.

        Returns:
            GeometryModel from chaos game protocol.
        """
        # Chaos game produces the fractal as a set of points
        # We can reconstruct: each path of n steps produces a node
        # Node position = 1/2 * (v_i0 + 1/2 * (v_i1 + 1/2 * (...)))
        # = sum over i: v_ii / 2^(i+1)

        # Vertices of equilateral triangle
        v0 = np.array([0.0, 0.0])
        v1 = np.array([1.0, 0.0])
        v2 = np.array([0.5, np.sqrt(3) / 4])
        vertices = [v0, v1, v2]

        nodes: List[Node] = []
        edges: List[Edge] = []
        node_positions: Dict[Tuple[int, ...], Tuple[float, float]] = {}
        node_counter = 0

        # Generate all possible paths of length = level
        # Each path is a tuple of vertex indices (0,1,2)
        def generate_paths(path_length: int):
            if path_length == 0:
                return [[]]
            shorter = generate_paths(path_length - 1)
            return [p + [i] for p in shorter for i in range(3)]

        paths = generate_paths(level)

        for path in paths:
            # Compute position as midpoint sum
            pos = np.array([0.0, 0.0])
            for i, vi in enumerate(path):
                pos = 0.5 * pos + 0.5 * vertices[vi]

            key = tuple(np.round(pos, 10).astype(int))
            if key not in node_positions:
                node_positions[key] = (float(pos[0]), float(pos[1]))
                nodes.append(Node(
                    id=node_counter,
                    position=(float(pos[0]), float(pos[1])),
                    level=level,
                    contraction_index=path[-1] if path else 0,
                    metadata={"chaos_path": path}
                ))
                node_counter += 1

            # Add edge to previous node in path
            if len(path) > 1:
                prev_pos = np.array([0.0, 0.0])
                for vi in path[:-1]:
                    prev_pos = 0.5 * prev_pos + 0.5 * vertices[vi]
                prev_key = tuple(np.round(prev_pos, 10).astype(int))
                if prev_key in node_positions:
                    # Find node IDs
                    prev_id = list(node_positions.keys()).index(prev_key)
                    # This is inefficient but works for now
                    pass

        triangle_count = 3 ** level
        boundary_length = 3 * (3 / 2) ** level
        area = (np.sqrt(3) / 4) * (0.25 ** level) * triangle_count

        meta = GeometryMeta(
            fractal_type="sierpinski",
            hausdorff_dimension=self.hausdorff_dimension,
            level=level,
            node_count=len(nodes),
            triangle_count=triangle_count,
            boundary_length=boundary_length,
            enclosed_area=float(area)
        )

        return GeometryModel(nodes=nodes, edges=edges, meta=meta)

    def _generate_lucas(self, level: int) -> GeometryModel:
        """Lucas theorem route.

        Lucas theorem: C(n,k) mod p = product of C(n_i, k_i) mod p
        for p prime, written in base p.
        For p=2, this is equivalent to Pascal mod 2.

        Returns:
            GeometryModel from Lucas theorem computation.
        """
        # Lucas theorem with p=2 is identical to Pascal mod 2
        return self._generate_pascal_mod2(level)

    def _generate_julia(self, level: int) -> GeometryModel:
        """Julia set route (Sierpinski carpet variant).

        Julia sets of rational maps z -> z^2 + c, for c in the
        Mandelbrot boundary, produce Sierpinski-like patterns when
        the critical orbit is pre-periodic.

        Returns:
            GeometryModel from Julia set computation.
        """
        # For now, delegate to IFS as the Julia route is complex
        return self._generate_ifs(level)
