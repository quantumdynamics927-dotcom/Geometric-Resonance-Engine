"""Quantum walk simulation on fractal graphs."""

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import scipy.linalg

from ..core.graph import GraphModel


@dataclass
class WalkResult:
    """Results from quantum walk simulation.

    Attributes:
        probabilities: Final probability distribution over nodes (normalized).
        position_entropy: Shannon entropy H = -Σ p log₂ p of position distribution.
        state_vector_history: (steps+1, N) complex amplitude array.
            Row i is the state vector after i steps.
        participation_ratio: PR = (Σ p_i)² / Σ p_i².
            = N for fully delocalized, → 1 for localized.
        state_transfer_fidelity: |⟨ψ₀|ψ_t⟩|² for specified source→target transfer.
        eigenstates: Complex eigenstates of the walk operator (if computed).
    """

    probabilities: np.ndarray
    position_entropy: float
    state_vector_history: np.ndarray
    participation_ratio: float
    state_transfer_fidelity: Optional[float] = None
    eigenstates: Optional[np.ndarray] = None


class QuantumWalkSimulator:
    """Simulate quantum walks on graph structures.

    Supports both **coined** and **staggered** quantum walk models:

    - **Coined walk**: Hilbert space = |position⟩ ⊗ |coin⟩.
      A separate "coin" operator mixes the internal degree of freedom
      at each step before the shift operator moves the walker.
      For a graph with max degree d, the coin dimension is 2 (left/right)
      or more generally d.

    - **Staggered walk**: Uses graph coloring to define alternating
      shift operators. No extra coin dimension needed.
      More natural for regular graphs and fractal topologies with
      3-fold symmetry (like Sierpinski's IFS structure).

    The **staggered walk** is the default because Sierpinski's 3-fold
    contraction symmetry maps naturally to 3-color graph coloring.
    """

    def __init__(self, graph: GraphModel):
        """Initialize simulator with a graph structure.

        Args:
            graph: GraphModel derived from a fractal geometry.
        """
        self.graph = graph
        self.n = graph.adjacency.shape[0]
        self.adjacency = graph.adjacency
        self.degree = graph.degree

    # -------------------------------------------------------------------------
    # Coined quantum walk
    # -------------------------------------------------------------------------

    def coined_walk(
        self,
        steps: int,
        initial_node: int = 0,
        coin: str = "grover"
    ) -> WalkResult:
        """Standard coined quantum walk on the graph.

        Hilbert space dimension = N × 2 (position ⊗ coin).
        Coin operators: "hadamard" (H), "grover" (diffusion), "fourier" (QFT).

        Args:
            steps: Number of walk steps to simulate.
            initial_node: Starting node index.
            coin: Coin type — "hadamard", "grover", or "fourier".

        Returns:
            WalkResult with probability distribution and metrics.
        """
        n = self.n

        # ---- Coin operator (2×2 for binary splitting) ----
        if coin == "hadamard":
            H = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)
        elif coin == "grover":
            H = 2 * np.ones((2, 2), dtype=complex) / 2 - np.eye(2, dtype=complex)
        elif coin == "fourier":
            omega = np.exp(2j * np.pi / 2)
            H = np.array([[1, 1], [1, omega]], dtype=complex) / np.sqrt(2)
        else:
            raise ValueError(f"Unknown coin type: {coin}")

        # ---- Shift operator ----
        # For each node i and each neighbor j, we need conditional shifts.
        # State indexing: state[i*2 + c] = amplitude at position i, coin c
        shift = self._build_coined_shift()

        # ---- Initial state: localized at initial_node, uniform coin ----
        state = np.zeros(n * 2, dtype=complex)
        state[initial_node * 2] = 1.0 / np.sqrt(2)
        state[initial_node * 2 + 1] = 1.0 / np.sqrt(2)

        # ---- Simulate ----
        history = [state.copy()]
        for _ in range(steps):
            # Apply coin then shift (standard coined walk order)
            state = self._apply_coined_coin(state, H)
            state = self._apply_coined_shift(state, shift)
            history.append(state.copy())

        history = np.array(history)

        # ---- Extract position probabilities (trace out coin) ----
        final = history[-1]
        probs = np.zeros(n)
        for i in range(n):
            probs[i] = abs(final[i * 2]) ** 2 + abs(final[i * 2 + 1]) ** 2
        probs = probs / np.sum(probs)

        return WalkResult(
            probabilities=probs,
            position_entropy=self._shannon_entropy(probs),
            state_vector_history=history,
            participation_ratio=self._participation_ratio(probs),
        )

    def _build_coined_shift(self) -> np.ndarray:
        """Build the shift operator for a coined walk on this graph.

        Returns:
            (2N, 2N) shift matrix where:
            - |i,0⟩ → |j,1⟩ for each edge i→j (first coin = move to neighbor)
            - |i,1⟩ → |i,0⟩ (stay, flip coin)
        """
        n = self.n
        shift = np.zeros((n * 2, n * 2), dtype=complex)

        for i in range(n):
            neighbors = []
            for j in range(n):
                if self.adjacency[i, j] > 0:
                    neighbors.append(j)

            if not neighbors:
                # Isolated node: stay
                shift[i * 2, i * 2] = 1.0
                shift[i * 2 + 1, i * 2 + 1] = 1.0
                continue

            # Coin=0: move to neighbor, flip to 1
            # We use uniform superposition over neighbors
            amp = 1.0 / np.sqrt(len(neighbors))
            for j in neighbors:
                shift[j * 2 + 1, i * 2] = amp

            # Coin=1: stay, flip to 0
            shift[i * 2, i * 2 + 1] = 1.0

        return shift

    def _apply_coined_coin(
        self, state: np.ndarray, coin: np.ndarray
    ) -> np.ndarray:
        """Apply coin operator to each position (tensor with identity)."""
        n = self.n
        new_state = np.zeros_like(state)
        for i in range(n):
            c0 = state[i * 2]
            c1 = state[i * 2 + 1]
            new_state[i * 2] = coin[0, 0] * c0 + coin[0, 1] * c1
            new_state[i * 2 + 1] = coin[1, 0] * c0 + coin[1, 1] * c1
        return new_state

    def _apply_coined_shift(
        self, state: np.ndarray, shift: np.ndarray
    ) -> np.ndarray:
        """Apply the pre-built shift operator."""
        return shift @ state

    # -------------------------------------------------------------------------
    # Staggered quantum walk
    # -------------------------------------------------------------------------

    def staggered_walk(
        self,
        steps: int,
        initial_node: int = 0
    ) -> WalkResult:
        """Staggered quantum walk using graph coloring.

        Uses the continuous-time quantum walk via the symmetric normalized Laplacian:
        U(t) = exp(-i * t * D^(-1/2) * A * D^(-1/2))

        This is always unitary regardless of graph coloring, unlike the
        discrete staggered model which requires careful handling of boundary nodes.
        The parameter t = pi/2 gives a natural "step" equivalent.

        Args:
            steps: Number of walk steps to simulate.
            initial_node: Starting node index.

        Returns:
            WalkResult with probability distribution and metrics.
        """
        n = self.n

        # Symmetric normalized Laplacian: L_sym = I - D^(-1/2) A D^(-1/2)
        # This is always symmetric and positive semi-definite.
        D_inv_sqrt = np.diag(1.0 / np.sqrt(self.degree))
        L_sym = np.eye(n) - D_inv_sqrt @ self.adjacency @ D_inv_sqrt

        # Walk operator: U = exp(-i * (pi/2) * L_sym)
        # Each application of U corresponds to one "step"
        theta = np.pi / 2
        U = scipy.linalg.expm(-1j * theta * L_sym)

        # Initial state
        state = np.zeros(n, dtype=complex)
        state[initial_node] = 1.0

        history = [state.copy()]
        for _ in range(steps):
            state = U @ state
            history.append(state.copy())

        history = np.array(history)

        # Final probabilities
        probs = np.abs(history[-1]) ** 2
        total = np.sum(probs)
        if total > 1e-15:
            probs = probs / total
        else:
            # Fully destructive interference: fall back to uniform
            probs = np.ones(n) / n

        return WalkResult(
            probabilities=probs,
            position_entropy=self._shannon_entropy(probs),
            state_vector_history=history,
            participation_ratio=self._participation_ratio(probs),
            eigenstates=None,
        )

    def _graph_coloring(self) -> np.ndarray:
        """Compute a proper graph coloring for staggered walk.

        Uses greedy 3-coloring with Dsatur (degree of saturation) ordering
        to maximize the chance of finding a valid 3-coloring for graphs
        that are 3-colorable (like Sierpinski).

        Returns:
            Array of shape (n,) with color values 0, 1, 2.
        """
        n = self.n
        adj_list = self.graph.adjacency_list()

        # Build adjacency sets for faster lookup
        neighbors = [set(adj_list[i]) for i in range(n)]

        # Greedy coloring with saturation ordering (Dsatur-inspired)
        colors = np.zeros(n, dtype=int) - 1  # -1 = uncolored
        available = [set(range(3)) for _ in range(n)]  # Available colors per node

        # Count colored neighbors and update available sets
        def update_available(node):
            used = {colors[nb] for nb in neighbors[node] if colors[nb] >= 0}
            available[node] = {c for c in range(3) if c not in used}

        # Initial: no nodes are colored, available = {0,1,2} for all
        for node in range(n):
            available[node] = {0, 1, 2}

        # Color nodes one by one
        colored_count = 0
        while colored_count < n:
            # Pick uncolored node with fewest available colors (Dsatur heuristic)
            # For ties, prefer higher degree
            candidates = [i for i in range(n) if colors[i] < 0]
            if not candidates:
                break

            best_node = None
            best_aval = 4  # > max colors
            best_degree = -1

            for node in candidates:
                if len(available[node]) < best_aval or (
                    len(available[node]) == best_aval
                    and len(neighbors[node]) > best_degree
                ):
                    best_node = node
                    best_aval = len(available[node])
                    best_degree = len(neighbors[node])

            # Assign smallest available color
            if best_node is not None and available[best_node]:
                chosen = min(available[best_node])
                colors[best_node] = chosen
                colored_count += 1

                # Update available sets for neighbors
                for nb in neighbors[best_node]:
                    available[nb].discard(chosen)
            else:
                # No available color (graph might not be 3-colorable)
                # Fall back to modulo coloring
                for node in candidates:
                    if colors[node] < 0:
                        colors[node] = node % 3
                break

        return colors

    def _build_staggered_shifts(
        self, colors: np.ndarray
    ) -> list:
        """Build staggered shift operators from coloring.

        For each color c, E_c is a reflection along edges of color c:
        E_c|i⟩ = Σ_{j: color[j]=next(c)} (A_ij / √deg) |j⟩

        Args:
            colors: Array of shape (n,) with color values.

        Returns:
            List of shift operator matrices, one per distinct color.
        """
        n = self.n
        distinct_colors = sorted(set(colors))
        m = len(distinct_colors)
        shifts = []

        for phase in range(m):
            c = distinct_colors[phase]
            next_c = distinct_colors[(phase + 1) % m]

            shift = np.zeros((n, n), dtype=complex)

            for i in range(n):
                if colors[i] != c:
                    continue

                # Find neighbors of color next_c
                neighbors_next = []
                for j in range(n):
                    if self.adjacency[i, j] > 0 and colors[j] == next_c:
                        neighbors_next.append(j)

                if not neighbors_next:
                    # No neighbor of next color: stay
                    shift[i, i] = 1.0
                else:
                    amp = 1.0 / np.sqrt(len(neighbors_next))
                    for j in neighbors_next:
                        shift[j, i] = amp

            shifts.append(shift)

        return shifts

    # -------------------------------------------------------------------------
    # State transfer fidelity
    # -------------------------------------------------------------------------

    def state_transfer_fidelity(
        self,
        source: int,
        target: int,
        steps: int = None
    ) -> float:
        """Measure quantum state transfer fidelity from source to target node.

        For optimal transfer, the walk exhibits periodic revival.
        For fractal graphs, the optimal steps often scale with the
        spectral gap and can exhibit 1/φ ≈ 0.618 behavior.

        Args:
            source: Source node index.
            target: Target node index.
            steps: If provided, measure at exactly these steps.
                   If None, scan up to 2*n steps and return maximum fidelity.

        Returns:
            Maximum |amplitude|² transfer fidelity observed.
        """
        if steps is not None:
            result = self.staggered_walk(steps=steps, initial_node=source)
            return float(abs(result.state_vector_history[-1][target]) ** 2)

        # Scan for optimal step count
        max_steps = self.n * 2
        max_fid = 0.0
        optimal_steps = 0

        for s in range(1, max_steps + 1):
            result = self.staggered_walk(steps=s, initial_node=source)
            fid = abs(result.state_vector_history[-1][target]) ** 2
            if fid > max_fid:
                max_fid = fid
                optimal_steps = s

        self._optimal_transfer_steps = optimal_steps
        return float(max_fid)

    # -------------------------------------------------------------------------
    # Entropy helpers
    # -------------------------------------------------------------------------

    def _shannon_entropy(self, probs: np.ndarray) -> float:
        """Compute Shannon entropy H = -Σ p log₂ p (in bits)."""
        p = probs[probs > 1e-15]
        return float(-np.sum(p * np.log2(p)))

    def _participation_ratio(self, probs: np.ndarray) -> float:
        """Participation ratio: PR = (Σ p_i)² / Σ p_i².

        = N for fully uniform (delocalized)
        → 1 for a single point (fully localized).
        """
        return float(np.sum(probs) ** 2 / np.sum(probs ** 2))

    def wave_propagation(
        self,
        initial_node: int,
        steps: int,
        damping: float = 0.0
    ) -> np.ndarray:
        """Simulate classical wave propagation (heat/diffusion) on the graph.

        Uses the graph Laplacian: d|ψ⟩/dt = -L|ψ⟩

        Args:
            initial_node: Source node for wave packet.
            steps: Number of diffusion steps.
            damping: Exponential damping coefficient.

        Returns:
            (steps+1, n) array of probability distributions over time.
        """
        n = self.n
        state = np.zeros(n)
        state[initial_node] = 1.0

        # Discrete-time diffusion: ψ(t+1) = (I - αL)ψ(t)
        alpha = 0.5 / np.max(self.degree) if np.max(self.degree) > 0 else 0.5
        diffusion_matrix = np.eye(n) - alpha * self.graph.laplacian

        history = [state.copy()]
        for _ in range(steps):
            state = diffusion_matrix @ state
            if damping > 0:
                state *= (1 - damping)
            history.append(state.copy())

        return np.array(history)
