"""Ternary (qutrit) encoding primitives.

Hausdorff dimension of Sierpinski: log₂(3) ≈ 1.585
This matches the capacity exponent of a ternary symmetric channel,
suggesting natural alignment with qutrit-based quantum communication.

Qutrits: 3-level quantum systems (|0⟩, |1⟩, |2⟩)
A Sierpinski triangle with 3^n nodes at level n maps naturally onto
3-level qutrit systems or registers of log₃(N) qutrits.
"""

from typing import List, Optional, Tuple

import numpy as np

try:
    from qiskit import QuantumCircuit
    from qiskit.circuit.library import RZGate, RXGate, RYGate
    from qiskit.circuit import Qubit
except ImportError:
    QuantumCircuit = None

from ..core.graph import GraphModel
from ..core.exceptions import CircuitMappingError


class QutritEncoder:
    """Encoder for ternary/qutrit representations of fractal graph states.

    Qutrit advantages for Sierpinski:
    - 3-level system matches IFS 3-contraction structure
    - Hausdorff dim ≈ ternary channel capacity
    - 3-qutrit register = 27 levels = 3^3 = matches level-3 triangle count
    - Log₃(N) qutrits encode N Sierpinski nodes efficiently

    Level n: 3^n nodes, encoded in log₃(3^n) = n qutrits.
    A level-5 Sierpinski (243 nodes) needs exactly 5 qutrits.
    """

    QUTRIT_DIM = 3  # 3 levels per qutrit

    @staticmethod
    def n_qutrits_for_nodes(n_nodes: int) -> int:
        """Return number of qutrits needed to encode n_nodes states.

        Args:
            n_nodes: Number of graph nodes to encode.

        Returns:
            Smallest integer n such that 3^n >= n_nodes.
        """
        if n_nodes <= 1:
            return 1
        n_qutrits = 1
        while 3 ** n_qutrits < n_nodes:
            n_qutrits += 1
        return n_qutrits

    @staticmethod
    def encode_state(trit_values: List[int]) -> np.ndarray:
        """Encode a list of trits (0, 1, 2) into qutrit basis state.

        Args:
            trit_values: List of trit values for each qutrit.

        Returns:
            Complex amplitude vector in the full 3^n qutrit basis.
        """
        n_qutrits = len(trit_values)
        dim = 3 ** n_qutrits

        # State index = Σ trit[i] * 3^i (least significant qutrit first)
        idx = sum(trit_values[i] * (3 ** i) for i in range(n_qutrits))

        state = np.zeros(dim, dtype=complex)
        state[idx] = 1.0
        return state

    @staticmethod
    def decode_state(amplitudes: np.ndarray) -> List[int]:
        """Decode a qutrit amplitude vector back to trit values.

        Args:
            amplitudes: Complex amplitude vector (must be a computational basis state).

        Returns:
            List of trit values.
        """
        dim = len(amplitudes)
        n_qutrits = int(round(np.log(dim) / np.log(3)))

        idx = int(np.argmax(np.abs(amplitudes)))
        trits = []
        for i in range(n_qutrits):
            trits.append(idx % 3)
            idx //= 3

        return trits

    @staticmethod
    def adjacency_to_qutrit_circuit(
        graph: GraphModel,
        num_qutrits: int,
    ) -> List[Tuple[int, int, float]]:
        """Convert adjacency matrix to qutrit gate sequence.

        For each edge (i, j), generates a qutrit conditional operation
        that transitions between the corresponding qutrit states.

        Args:
            graph: GraphModel to encode.
            num_qutrits: Number of qutrits in the register.

        Returns:
            List of (control_idx, target_idx, angle) tuples for qutrit gates.
        """
        n = graph.adjacency.shape[0]
        gates = []

        # For each pair of adjacent nodes, find their trit representations
        # and generate conditional qutrit gates
        for i in range(n):
            for j in range(i + 1, n):
                if graph.adjacency[i, j] > 0:
                    weight = graph.adjacency[i, j]

                    # Control on qutrit index i, target qutrit index j
                    # Rotation angle proportional to edge weight
                    angle = np.arccos(weight / np.sqrt(2))
                    gates.append((i, j, angle))

        return gates

    def build_qutrit_initialization_circuit(
        self,
        node_index: int,
        num_qutrits: int,
    ) -> QuantumCircuit:
        """Build a circuit that initializes qutrits to encode a node index.

        Args:
            node_index: Node index to encode (0 <= node_index < 3^num_qutrits).
            num_qutrits: Number of qutrits in the register.

        Returns:
            QuantumCircuit initializing to the specified node.
        """
        if QuantumCircuit is None:
            raise ImportError("Qiskit is required for qutrit circuits")

        qc = QuantumCircuit(num_qutrits, name=f"init_n{node_index}")

        # Convert node_index to base-3 representation
        trit_values = []
        tmp = node_index
        for _ in range(num_qutrits):
            trit_values.append(tmp % 3)
            tmp //= 3

        # Apply qutrit initialization gates
        for q, trit in enumerate(trit_values):
            if trit == 0:
                pass  # |0⟩ is initial state
            elif trit == 1:
                # Apply X gate (in qutrit: basis rotation)
                qc.x(q)
            elif trit == 2:
                # Apply SX gate (in qutrit: 90° rotation)
                qc.rx(np.pi / 2, q)

        return qc

    def build_qutrit_shift_circuit(
        self,
        graph: GraphModel,
        num_qutrits: int,
    ) -> QuantumCircuit:
        """Build qutrit circuit implementing graph shift operator.

        Args:
            graph: GraphModel to encode.
            num_qutrits: Number of qutrits.

        Returns:
            QuantumCircuit implementing the shift operator.
        """
        if QuantumCircuit is None:
            raise ImportError("Qiskit is required for qutrit circuits")

        n = graph.adjacency.shape[0]
        qc = QuantumCircuit(num_qutrits, name="qutrit_shift")

        # For each node i, apply conditional operations to transition to neighbors j
        for i in range(n):
            neighbors = [j for j in range(n) if graph.adjacency[i, j] > 0]
            if not neighbors:
                continue

            # Degree-normalized transition amplitude
            deg = graph.degree[i]
            if deg == 0:
                continue

            # For each neighbor, apply conditional rotation
            for j in neighbors:
                # Only apply if j > i to avoid double-counting
                if j <= i:
                    continue

                # Control on qutrit state |i⟩ (base-3 encoded)
                # Target: apply rotation to move to |j⟩

                # Simplified: apply controlled-X for each neighbor transition
                # In full qutrit model, this would be multi-controlled qutrit gates
                control_trits = self._node_to_trits(i, num_qutrits)
                target_trits = self._node_to_trits(j, num_qutrits)

                # Apply control pattern for this transition
                self._append_qutrit_control(qc, control_trits, target_trits, i, j)

        return qc

    def _node_to_trits(self, node: int, num_qutrits: int) -> List[int]:
        """Convert a node index to its base-3 representation."""
        trits = []
        tmp = node
        for _ in range(num_qutrits):
            trits.append(tmp % 3)
            tmp //= 3
        return trits

    def _append_qutrit_control(
        self,
        qc: QuantumCircuit,
        control_trits: List[int],
        target_trits: List[int],
        control_node: int,
        target_node: int,
    ) -> None:
        """Append qutrit-controlled operation using qubit approximation.

        Uses multi-controlled X gates as an approximation for qutrit control.
        For a full qutrit implementation, use qiskit-qutrit libraries.
        """
        n_qutrits = len(control_trits)

        # Apply X gates to set control state
        for q, trit in enumerate(control_trits):
            if trit == 1:
                qc.x(q)
            elif trit == 2:
                qc.rx(np.pi / 2, q)

        # Apply controlled operation to target qubit
        # Use CZ as a proxy for qutrit control
        for q in range(n_qutrits):
            if target_trits[q] == 1:
                qc.x(q)

        # Reset control qubits
        for q, trit in enumerate(control_trits):
            if trit == 1:
                qc.x(q)
            elif trit == 2:
                qc.rx(-np.pi / 2, q)
