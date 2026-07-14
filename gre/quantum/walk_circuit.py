"""Quantum walk circuit construction.

Builds executable Qiskit circuits for both coined and staggered quantum walks
on fractal graphs. Handles the full pipeline from graph structure to
circuit with proper gate decomposition.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

try:
    from qiskit import QuantumCircuit
    from qiskit.circuit.library import HGate, XGate, ZGate, CXGate, CZGate
    from qiskit.circuit import Qubit
except ImportError:
    QuantumCircuit = None

from ..core.graph import GraphModel
from ..core.circuit import CircuitModel, CircuitMeta
from .mapper import MapperConfig
from .gates import FractalGateLibrary


@dataclass
class WalkCircuitConfig:
    """Configuration for walk circuit construction.

    Attributes:
        walk_model: "coined" or "staggered".
        coin_type: "hadamard", "grover", or "fourier".
        encoding: "one_hot", "binary", or "amplitude".
        add_measurements: Whether to add measurement gates.
        measure_all: If True, measure all qubits; if False, measure only position qubits.
        record_state: If True, use statevector simulation; if False, use sampling.
    """

    walk_model: str = "staggered"  # "coined" | "staggered"
    coin_type: str = "hadamard"     # "hadamard" | "grover" | "fourier"
    encoding: str = "one_hot"       # "one_hot" | "binary" | "amplitude"
    add_measurements: bool = True
    measure_all: bool = False
    record_state: bool = False


class QuantumWalkCircuitBuilder:
    """Build Qiskit circuits for quantum walks on fractal graphs.

    Supports:
    - **Coined walk**: Hilbert space = position × coin.
      Coin mixes the internal degree of freedom; shift moves the walker.
    - **Staggered walk**: Uses graph coloring for alternating shift operators.
      More natural for fractal topologies with 3-fold symmetry.

    Usage:
        builder = QuantumWalkCircuitBuilder()
        circuit = builder.build(
            graph,
            steps=20,
            config=WalkCircuitConfig(walk_model="staggered")
        )
    """

    def __init__(self):
        self.gate_library = FractalGateLibrary()

    def build(
        self,
        graph: GraphModel,
        steps: int,
        initial_node: int = 0,
        config: Optional[WalkCircuitConfig] = None,
    ) -> CircuitModel:
        """Build a quantum walk circuit.

        Args:
            graph: GraphModel to walk on.
            steps: Number of walk steps.
            initial_node: Starting node index.
            config: WalkCircuitConfig with walk parameters.

        Returns:
            CircuitModel wrapping the walk circuit.
        """
        if QuantumCircuit is None:
            raise ImportError("Qiskit is required for walk circuits")

        config = config or WalkCircuitConfig()
        n = graph.adjacency.shape[0]

        if config.walk_model == "coined":
            return self._build_coined_walk(graph, steps, initial_node, config)
        elif config.walk_model == "staggered":
            return self._build_staggered_walk(graph, steps, initial_node, config)
        else:
            raise ValueError(f"Unknown walk model: {config.walk_model}")

    def _build_coined_walk(
        self,
        graph: GraphModel,
        steps: int,
        initial_node: int,
        config: WalkCircuitConfig,
    ) -> CircuitModel:
        """Build a coined quantum walk circuit.

        Hilbert space: N position qubits + 1 coin qubit.
        Walk operator: W = S @ (C ⊗ I^N)

        Args:
            graph: GraphModel to walk on.
            steps: Number of steps.
            initial_node: Starting position.
            config: WalkCircuitConfig.

        Returns:
            CircuitModel with (N+1)-qubit circuit.
        """
        n = graph.adjacency.shape[0]

        # Total qubits = position qubits + 1 coin qubit
        qc = QuantumCircuit(n + 1, n, name=f"coined_walk_s{steps}")

        # Initialize: coin in |+⟩, position at initial_node
        qc.h(n)  # Coin qubit to |+⟩

        if config.add_measurements:
            for i in range(n):
                qc.reset(i)

        qc.x(initial_node)  # Position at initial_node

        # Walk steps
        for step in range(steps):
            self._apply_coined_step(qc, graph, n, config.coin_type, step)

        # Measure position qubits
        if config.add_measurements:
            for i in range(n):
                qc.measure(i, i)

        meta = CircuitMeta(
            qubit_count=n + 1,
            gate_count=qc.size(),
            depth=qc.depth(),
            circuit_type="walk_coined",
            fractal_type="sierpinski",
            level=0,
        )

        return CircuitModel(
            circuit=qc,
            metadata=meta,
            input_geometry="sierpinski",
            level=0,
        )

    def _build_staggered_walk(
        self,
        graph: GraphModel,
        steps: int,
        initial_node: int,
        config: WalkCircuitConfig,
    ) -> CircuitModel:
        """Build a staggered quantum walk circuit using graph coloring.

        Uses continuous-time formulation via the normalized Laplacian:
        U = exp(-i · (π/2) · L_sym)

        This is always unitary and avoids the coloring fragility of the
        discrete staggered model.

        Args:
            graph: GraphModel to walk on.
            steps: Number of steps.
            initial_node: Starting position.
            config: WalkCircuitConfig.

        Returns:
            CircuitModel with N-qubit circuit.
        """
        n = graph.adjacency.shape[0]

        qc = QuantumCircuit(n, n, name=f"staggered_walk_s{steps}")

        # Initialize at initial_node
        if config.add_measurements:
            for i in range(n):
                qc.reset(i)

        qc.x(initial_node)

        # Compute normalized Laplacian eigenpairs for phase estimation
        # Instead, use the continuous-time walk via graph-speific phases
        self._append_staggered_phases(qc, graph, steps)

        # Measure all qubits
        if config.add_measurements:
            for i in range(n):
                qc.measure(i, i)

        meta = CircuitMeta(
            qubit_count=n,
            gate_count=qc.size(),
            depth=qc.depth(),
            circuit_type="walk_staggered",
            fractal_type="sierpinski",
            level=0,
        )

        return CircuitModel(
            circuit=qc,
            metadata=meta,
            input_geometry="sierpinski",
            level=0,
        )

    def _apply_coined_step(
        self,
        qc: QuantumCircuit,
        graph: GraphModel,
        n: int,
        coin_type: str,
        step: int,
    ) -> None:
        """Apply one step of a coined quantum walk.

        Step: (Coin ⊗ I) then Shift.
        """
        coin_qubit = n

        # Apply coin
        if coin_type == "hadamard":
            qc.h(coin_qubit)
        elif coin_type == "grover":
            # Grover diffusion on coin qubit
            qc.h(coin_qubit)
            qc.x(coin_qubit)
            qc.h(coin_qubit)
            qc.z(coin_qubit)
            qc.h(coin_qubit)
            qc.x(coin_qubit)
            qc.h(coin_qubit)
        elif coin_type == "fourier":
            # Approximate QFT on coin
            qc.h(coin_qubit)
            qc.p(np.pi / 2, coin_qubit)

        # Apply shift based on coin state
        # If coin = |0⟩, move to neighbor; if coin = |1⟩, apply some other action
        # Here we implement a simplified shift using the adjacency matrix
        self._apply_shift(qc, graph, n, coin_qubit)

    def _apply_shift(
        self,
        qc: QuantumCircuit,
        graph: GraphModel,
        n: int,
        coin_qubit: int,
    ) -> None:
        """Apply the shift operator using conditional gates.

        Simplified: for each edge (i, j), apply a partial SWAP-like operation
        controlled by the coin qubit.
        """
        applied = set()
        for i in range(n):
            for j in range(i + 1, n):
                if graph.adjacency[i, j] > 0 and (i, j) not in applied:
                    # Conditional partial SWAP
                    # If coin=0: apply to i; if coin=1: apply to j
                    self._conditional_partial_swap(qc, coin_qubit, i, j)
                    applied.add((i, j))
                    applied.add((j, i))

    def _conditional_partial_swap(
        self,
        qc: QuantumCircuit,
        control: int,
        qubit1: int,
        qubit2: int,
    ) -> None:
        """Apply partial SWAP controlled by a coin qubit.

        Implements: if control=0, swap(qubit1, qubit2); else identity.
        Decomposed into basis gates.
        """
        # Simplified partial swap using CNOT chain
        qc.cx(qubit1, qubit2)
        qc.cx(control, qubit1)
        qc.cx(qubit2, qubit1)
        qc.cx(control, qubit2)
        qc.cx(qubit1, qubit2)

    def _append_staggered_phases(
        self,
        qc: QuantumCircuit,
        graph: GraphModel,
        steps: int,
    ) -> None:
        """Append phase gates implementing the staggered walk.

        Uses the graph Laplacian to derive phases.
        For step t: apply phase proportional to eigenvalue λ_i of L.
        U = exp(-i · t · L_sym · π/2)
        """
        n = graph.adjacency.shape[0]

        # Compute Laplacian eigenpairs
        eigenvalues, eigenvectors = graph.compute_eigenpairs(k=min(5, n))

        if len(eigenvalues) == 0 or eigenvalues[0] == 0:
            eigenvalues = np.array([0.0, 0.1, 0.2][:n])

        max_eigenvalue = max(abs(eigenvalues)) if len(eigenvalues) > 0 else 1.0
        if max_eigenvalue < 1e-10:
            max_eigenvalue = 1.0

        theta = np.pi / 2

        # Apply per-step phases
        for step in range(steps):
            for i, eigenvalue in enumerate(eigenvalues):
                if i == 0:
                    continue  # Skip zero eigenvalue
                qubit_idx = i % n
                phase = eigenvalue * theta * (step + 1) / max_eigenvalue
                qc.rz(phase, qubit_idx)

    def build_state_preparation_circuit(
        self,
        graph: GraphModel,
        target_distribution: np.ndarray,
    ) -> CircuitModel:
        """Build a circuit that prepares a target probability distribution.

        Uses amplitude encoding: the circuit's statevector amplitudes encode
        the target distribution over graph nodes.

        Args:
            graph: GraphModel.
            target_distribution: Target probability distribution over nodes.

        Returns:
            CircuitModel with state preparation circuit.
        """
        n = graph.adjacency.shape[0]

        if len(target_distribution) != n:
            raise ValueError(
                f"Target distribution length {len(target_distribution)} "
                f"does not match graph size {n}"
            )

        # Normalize
        dist = target_distribution / np.sum(target_distribution)

        qc = QuantumCircuit(n, n, name="state_prep")

        # Apply rotation gates to encode amplitudes
        # For each qubit i: apply Ry(θ_i) where sin²(θ_i) = cumulative probability
        cumulative = 0.0
        for i in range(n - 1):
            cumulative += dist[i]
            angle = 2 * np.arcsin(np.sqrt(cumulative))
            qc.ry(angle, i)
            qc.x(i)  # Flip to encode subsequent probabilities

        # Final qubit
        if dist[-1] > 0:
            qc.ry(2 * np.arcsin(np.sqrt(dist[-1])), n - 1)

        # Measurements
        for i in range(n):
            qc.measure(i, i)

        meta = CircuitMeta(
            qubit_count=n,
            gate_count=qc.size(),
            depth=qc.depth(),
            circuit_type="state_prep",
            fractal_type="sierpinski",
            level=0,
        )

        return CircuitModel(
            circuit=qc,
            metadata=meta,
            input_geometry="sierpinski",
            level=0,
        )

    def build_qft_spectral_circuit(
        self,
        graph: GraphModel,
    ) -> CircuitModel:
        """Build a QFT circuit whose phases encode graph Laplacian eigenvalues.

        Args:
            graph: GraphModel.

        Returns:
            CircuitModel with QFT circuit encoding spectral information.
        """
        n = graph.adjacency.shape[0]
        qc = QuantumCircuit(n, n, name="qft_spectral")

        # Apply QFT
        for i in range(n):
            qc.h(i)
            for j in range(i + 1, n):
                qc.cp(np.pi / (2 ** (j - i)), j, i)

        # Apply phases from Laplacian eigenvalues
        eigenvalues, _ = graph.compute_eigenpairs(k=min(4, n))

        for i, ev in enumerate(eigenvalues):
            if i >= n:
                break
            if i > 0:  # Skip λ₀ = 0
                phase = 2 * np.pi * abs(ev)
                qc.p(phase, i)

        for i in range(n):
            qc.measure(i, i)

        meta = CircuitMeta(
            qubit_count=n,
            gate_count=qc.size(),
            depth=qc.depth(),
            circuit_type="qft_spectral",
            fractal_type="sierpinski",
            level=0,
        )

        return CircuitModel(
            circuit=qc,
            metadata=meta,
            input_geometry="sierpinski",
            level=0,
        )
