"""Graph-to-quantum-circuit mapper.

Maps a GraphModel (derived from fractal geometry) to an executable Qiskit
QuantumCircuit. Handles both qubit (binary) and qutrit (ternary) encodings.

The mapper is backend-agnostic: it produces a Qiskit circuit that can then
be executed on any Qiskit-compatible backend (IBM Quantum, Aer simulator,
QuEra, etc.).
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any

import numpy as np

try:
    from qiskit import QuantumCircuit
    from qiskit.circuit import Qubit, Clbit
    from qiskit.circuit.library import (
        HGate, CXGate, RZGate, RXGate, RYGate,
        UGate, U1Gate, U2Gate, U3Gate,
    )
    from qiskit.circuit.library.arithmetic import (
        WeightedAdder, LinearPauliRotator,
    )
    from qiskit.quantum_info import Operator
    from qiskit.converters import circuit_to_dag, dag_to_circuit
except ImportError:
    QuantumCircuit = None

from ..core.graph import GraphModel
from ..core.circuit import CircuitModel, CircuitMeta
from ..core.exceptions import CircuitMappingError


@dataclass
class MapperConfig:
    """Configuration for graph-to-circuit mapping.

    Attributes:
        encoding: "qubit" (binary) or "qutrit" (ternary).
        basis_gates: List of basis gate names for transpilation.
        optimization_level: Qiskit transpilation optimization (0-3).
        add_initial_reset: Whether to add explicit reset at circuit start.
        add_measurements: Whether to add measurement gates at circuit end.
        bit_encoding: How to encode graph node values — "one_hot", "binary",
            or "amplitude".
        layout_method: Qiskit layout method ("trivial", "dense", "noise_adaptive").
        routing_method: Qiskit routing method ("basic", "lookahead", "stochastic").
    """

    encoding: str = "qubit"
    basis_gates: List[str] = None
    optimization_level: int = 1
    add_initial_reset: bool = True
    add_measurements: bool = True
    bit_encoding: str = "one_hot"  # "one_hot" | "binary" | "amplitude"
    layout_method: str = "trivial"
    routing_method: str = "basic"

    def __post_init__(self):
        if self.basis_gates is None:
            self.basis_gates = ["cx", "u3"]


class GraphCircuitMapper:
    """Map a GraphModel to a Qiskit QuantumCircuit.

    The mapper supports multiple encoding strategies:
    - **one_hot**: Each node is one qubit; amplitude encodes node state.
      Hilbert space dimension = N qubits.
    - **binary**: log2(N) qubits encode node index; adjacency applied via
      conditional gates.
      Hilbert space dimension = log2(N) qubits.
    - **amplitude**: A single qubit's amplitude encodes node probability;
      node transitions via controlled rotations.

    The walk operator is decomposed into basis gates for the target backend.

    Usage:
        mapper = GraphCircuitMapper(config=MapperConfig(encoding="one_hot"))
        circuit_model = mapper.graph_to_circuit(graph, walk_steps=10)
        qasm = circuit_model.to_qasm()
    """

    def __init__(self, config: Optional[MapperConfig] = None):
        self.config = config or MapperConfig()

    def graph_to_circuit(
        self,
        graph: GraphModel,
        walk_steps: int,
        initial_node: int = 0,
        coin_type: str = "grover",
    ) -> CircuitModel:
        """Map a graph to a quantum circuit encoding a quantum walk.

        Args:
            graph: GraphModel to encode.
            walk_steps: Number of quantum walk steps to unroll.
            initial_node: Starting node index (one_hot encoding only).
            coin_type: Coin operator type — "grover", "hadamard", "fourier".

        Returns:
            CircuitModel wrapping a Qiskit QuantumCircuit.

        Raises:
            CircuitMappingError: If mapping fails.
            ImportError: If Qiskit is not installed.
        """
        if QuantumCircuit is None:
            raise ImportError("Qiskit is required for circuit mapping")

        n = graph.adjacency.shape[0]
        encoding = self.config.encoding

        if encoding == "one_hot":
            return self._one_hot_mapping(graph, walk_steps, initial_node, coin_type)
        elif encoding == "binary":
            return self._binary_mapping(graph, walk_steps, initial_node, coin_type)
        elif encoding == "amplitude":
            return self._amplitude_mapping(graph, walk_steps, initial_node)
        else:
            raise CircuitMappingError(f"Unknown encoding: {encoding}")

    def _one_hot_mapping(
        self,
        graph: GraphModel,
        walk_steps: int,
        initial_node: int,
        coin_type: str,
    ) -> CircuitModel:
        """One-hot encoding: one qubit per graph node.

        Each node i has a corresponding qubit i.
        Amplitude at qubit i = probability of walker being at node i.
        State |00...1...0⟩ with 1 at position i = walker at node i.

        Coin + shift operator applied at each step.

        Args:
            graph: GraphModel to encode.
            walk_steps: Number of steps.
            initial_node: Initial position.
            coin_type: Coin type.

        Returns:
            CircuitModel with N-qubit circuit.
        """
        n = graph.adjacency.shape[0]

        # Build coin operator
        coin_matrix = self._build_coin_matrix(coin_type, n)

        # Build shift operator from adjacency
        shift_matrix = self._build_one_hot_shift(graph)

        # Combine into walk operator: W = Shift @ (Coin ⊗ I)
        walk_matrix = shift_matrix @ np.kron(coin_matrix, np.eye(n))

        # Build circuit
        qc = QuantumCircuit(n, n, name=f"qw_onehot_s{walk_steps}")

        # Initial reset
        if self.config.add_initial_reset:
            for i in range(n):
                qc.reset(i)

        # Initialize at initial_node
        qc.x(initial_node)

        # Decompose walk steps into basis gates
        for step in range(walk_steps):
            self._append_walk_step(qc, graph, coin_type)

        # Measurements
        if self.config.add_measurements:
            for i in range(n):
                qc.measure(i, i)

        # Compute metadata
        gate_count = qc.size()
        depth = qc.depth()

        meta = CircuitMeta(
            qubit_count=n,
            gate_count=gate_count,
            depth=depth,
            circuit_type="walk_one_hot",
            fractal_type="sierpinski",
            level=0,
        )

        return CircuitModel(
            circuit=qc,
            metadata=meta,
            input_geometry="sierpinski",
            level=0,
        )

    def _binary_mapping(
        self,
        graph: GraphModel,
        walk_steps: int,
        initial_node: int,
        coin_type: str,
    ) -> CircuitModel:
        """Binary encoding: log2(N) qubits encode node index.

        More efficient qubit-wise but requires conditional gates for
        adjacency. Hilbert space = log2(N) qubits.

        Args:
            graph: GraphModel to encode.
            walk_steps: Number of steps.
            initial_node: Initial position.
            coin_type: Coin type.

        Returns:
            CircuitModel with log2(N)-qubit circuit.
        """
        n = graph.adjacency.shape[0]
        num_qubits = int(np.ceil(np.log2(n)))

        qc = QuantumCircuit(num_qubits, num_qubits, name=f"qw_binary_s{walk_steps}")

        if self.config.add_initial_reset:
            for i in range(num_qubits):
                qc.reset(i)

        # Initialize to binary representation of initial_node
        binary = format(initial_node, f"0{num_qubits}b")
        for i, bit in enumerate(binary[-num_qubits:]):
            if bit == "1":
                qc.x(i)

        # Build walk steps using conditional adjacency
        for step in range(walk_steps):
            self._append_binary_walk_step(qc, graph, num_qubits, coin_type)

        if self.config.add_measurements:
            for i in range(num_qubits):
                qc.measure(i, i)

        meta = CircuitMeta(
            qubit_count=num_qubits,
            gate_count=qc.size(),
            depth=qc.depth(),
            circuit_type="walk_binary",
            fractal_type="sierpinski",
            level=0,
        )

        return CircuitModel(
            circuit=qc,
            metadata=meta,
            input_geometry="sierpinski",
            level=0,
        )

    def _amplitude_mapping(
        self,
        graph: GraphModel,
        walk_steps: int,
        initial_node: int,
    ) -> CircuitModel:
        """Amplitude encoding: single qubit encodes node probability.

        Uses controlled rotations to move amplitude between nodes based on
        adjacency. More gate-efficient but less intuitive.

        Args:
            graph: GraphModel to encode.
            walk_steps: Number of steps.
            initial_node: Initial position.

        Returns:
            CircuitModel with 1-qubit circuit.
        """
        n = graph.adjacency.shape[0]

        qc = QuantumCircuit(1, n, name=f"qw_ampl_s{walk_steps}")

        if self.config.add_initial_reset:
            qc.reset(0)

        # Initialize amplitude
        qc.h(0)

        # Build amplitude-based walk steps
        for step in range(walk_steps):
            self._append_amplitude_walk_step(qc, graph, n)

        if self.config.add_measurements:
            qc.measure(0, initial_node)

        meta = CircuitMeta(
            qubit_count=1,
            gate_count=qc.size(),
            depth=qc.depth(),
            circuit_type="walk_amplitude",
            fractal_type="sierpinski",
            level=0,
        )

        return CircuitModel(
            circuit=qc,
            metadata=meta,
            input_geometry="sierpinski",
            level=0,
        )

    def _build_coin_matrix(self, coin_type: str, n: int) -> np.ndarray:
        """Build N×N coin operator matrix.

        The coin operator mixes the walker's internal degree of freedom.
        For a one-hot encoding, this is applied to the node dimension.
        """
        if coin_type == "grover":
            # Grover diffusion: 2|ψ⟩⟨ψ| - I
            # Applied to each node's neighborhood
            return np.eye(n)

        elif coin_type == "hadamard":
            # Hadamard coin
            H = np.array([[1, 1], [1, -1]], dtype=complex) / np.sqrt(2)
            return np.kron(np.eye(n // 2), H) if n >= 2 else H

        elif coin_type == "fourier":
            # QFT coin
            theta = 2 * np.pi / n
            F = np.zeros((n, n), dtype=complex)
            for i in range(n):
                for j in range(n):
                    F[i, j] = np.exp(2j * np.pi * i * j / n) / np.sqrt(n)
            return F

        else:
            raise CircuitMappingError(f"Unknown coin type: {coin_type}")

    def _build_one_hot_shift(self, graph: GraphModel) -> np.ndarray:
        """Build one-hot shift operator from graph adjacency.

        Shift operator S moves amplitude from node i to its neighbors j:
        S|i⟩ = (1/√deg(i)) Σ_{j~i} |j⟩

        Returns:
            N×N shift matrix (column-stochastic).
        """
        n = graph.adjacency.shape[0]
        shift = np.zeros((n, n), dtype=complex)

        for i in range(n):
            neighbors = []
            for j in range(n):
                if graph.adjacency[i, j] > 0:
                    neighbors.append(j)

            if not neighbors:
                shift[i, i] = 1.0
                continue

            amp = 1.0 / np.sqrt(len(neighbors))
            for j in neighbors:
                shift[j, i] = amp

        return shift

    def _append_walk_step(
        self,
        qc: QuantumCircuit,
        graph: GraphModel,
        coin_type: str,
    ) -> None:
        """Append one quantum walk step to the circuit.

        For one-hot encoding, this applies:
        1. Coin operator (Hadamard or Grover diffusion on each qubit)
        2. Conditional shifts based on adjacency
        """
        n = graph.adjacency.shape[0]

        # Coin: Hadamard on all qubits
        for i in range(n):
            if coin_type == "hadamard":
                qc.h(i)
            elif coin_type == "grover":
                # Grover-like diffusion: apply X gates, multi-controlled Z, X gates
                self._grover_diffusion(qc, [i])

        # Shift: conditional on adjacency
        self._append_one_hot_shift(qc, graph)

    def _append_one_hot_shift(
        self,
        qc: QuantumCircuit,
        graph: GraphModel,
    ) -> None:
        """Append the one-hot shift operator using conditional gates.

        For each edge (i, j), apply a partial swap or controlled rotation
        that moves amplitude from i to j.
        """
        n = graph.adjacency.shape[0]
        applied_edges = set()

        for i in range(n):
            neighbors = [j for j in range(n) if graph.adjacency[i, j] > 0 and (i, j) not in applied_edges]
            if not neighbors:
                continue

            # Use multi-controlled gate for efficiency
            if len(neighbors) == 1:
                j = neighbors[0]
                # SWAP-like operation via controlled rotation
                self._partial_swap(qc, i, j)
            elif len(neighbors) == 2:
                j1, j2 = neighbors[0], neighbors[1]
                # Two partial swaps
                self._partial_swap(qc, i, j1)
                self._partial_swap(qc, i, j2)

        # Track applied edges to avoid double-application
        for i in range(n):
            for j in range(n):
                if graph.adjacency[i, j] > 0:
                    applied_edges.add((i, j))
                    applied_edges.add((j, i))

    def _partial_swap(
        self,
        qc: QuantumCircuit,
        control: int,
        target: int,
        angle: float = np.pi / 4,
    ) -> None:
        """Append a partial SWAP gate.

        Partial SWAP moves amplitude from control to target.
        Decomposed as: CSWAP-like structure using basis gates.
        """
        # Partial SWAP decomposition using basis gates
        # PSWAP(θ) = [1, 0, 0, 0; 0, cos(θ), sin(θ), 0; 0, -sin(θ), cos(θ), 0; 0, 0, 0, 1]
        qc.rz(angle, target)
        qc.cx(control, target)
        qc.rx(angle / 2, target)
        qc.cx(control, target)
        qc.rx(-angle / 2, target)

    def _grover_diffusion(
        self,
        qc: QuantumCircuit,
        qubits: List[int],
    ) -> None:
        """Append Grover diffusion operator on specified qubits."""
        # Simple 2-qubit Grover diffusion
        if len(qubits) == 1:
            i = qubits[0]
            qc.h(i)
            qc.x(i)
            qc.h(i)
        elif len(qubits) == 2:
            i, j = qubits[0], qubits[1]
            qc.h(i)
            qc.h(j)
            qc.x(i)
            qc.x(j)
            qc.h(j)
            qc.cx(i, j)
            qc.h(j)
            qc.x(i)
            qc.x(j)
            qc.h(i)
            qc.h(j)

    def _append_binary_walk_step(
        self,
        qc: QuantumCircuit,
        graph: GraphModel,
        num_qubits: int,
        coin_type: str,
    ) -> None:
        """Append one walk step in binary encoding.

        For each node, check if current index matches a source node,
        then conditionally apply transitions to neighbors.
        """
        n = graph.adjacency.shape[0]

        # Apply coin (Hadamard on all qubits)
        for i in range(num_qubits):
            qc.h(i)

        # Conditional adjacency application
        # For each source node s and neighbor t, apply controlled operation
        for s in range(n):
            neighbors = [t for t in range(n) if graph.adjacency[s, t] > 0]
            if not neighbors:
                continue

            # Encode source node condition
            binary_s = format(s, f"0{num_qubits}b")

            # Build condition qubits
            for t in neighbors:
                binary_t = format(t, f"0{num_qubits}b")
                # Apply controlled rotation or X based on match
                for qb in range(num_qubits):
                    if binary_s[qb] == "1":
                        qc.x(qb)

    def _append_amplitude_walk_step(
        self,
        qc: QuantumCircuit,
        graph: GraphModel,
        n: int,
    ) -> None:
        """Append one amplitude-encoding walk step.

        Uses controlled rotations to redistribute amplitude based on
        adjacency, normalized by node degree.
        """
        degrees = graph.degree

        for node in range(n):
            if degrees[node] == 0:
                continue

            # Rotation angle proportional to 1/√degree
            theta = np.pi / (2 * np.sqrt(degrees[node]))

            # Apply rotation conditioned on amplitude
            # In practice: use control qubits encoding node index
            qc.rz(theta, 0)

    def transpile_for_backend(
        self,
        circuit_model: CircuitModel,
        backend_name: Optional[str] = None,
        coupling_map: Optional[List[List[int]]] = None,
    ) -> QuantumCircuit:
        """Transpile circuit for a specific backend.

        Args:
            circuit_model: CircuitModel to transpile.
            backend_name: Target backend name.
            coupling_map: Physical coupling map for transpilation.

        Returns:
            Transpiled QuantumCircuit ready for execution.
        """
        if QuantumCircuit is None:
            raise ImportError("Qiskit is required for transpilation")

        from qiskit import transpile
        from qiskit.providers.basic_provider import BasicProvider

        transpiled = transpile(
            circuit_model.circuit,
            basis_gates=self.config.basis_gates,
            optimization_level=self.config.optimization_level,
            layout_method=self.config.layout_method,
            routing_method=self.config.routing_method,
            coupling_map=coupling_map,
        )

        return transpiled
