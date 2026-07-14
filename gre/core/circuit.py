"""Quantum circuit representations derived from graph structures."""

from dataclasses import dataclass
from typing import Optional

import numpy as np

try:
    from qiskit import QuantumCircuit
except ImportError:
    QuantumCircuit = None  # type: ignore

from .geometry import GeometryModel, GeometryMeta


@dataclass
class CircuitMeta:
    """Metadata for a generated quantum circuit.

    Attributes:
        qubit_count: Number of physical qubits required.
        gate_count: Total number of gates in circuit.
        depth: Circuit depth (critical path length).
        circuit_type: One of "walk", "state_prep", "validation".
        fractal_type: Fractal type used (e.g., "sierpinski").
        level: Fractal recursion level.
    """

    qubit_count: int
    gate_count: int
    depth: int
    circuit_type: str
    fractal_type: str
    level: int


@dataclass
class CircuitModel:
    """Quantum circuit derived from a fractal graph.

    Attributes:
        circuit: Qiskit QuantumCircuit instance.
        metadata: CircuitMeta instance with circuit statistics.
        input_geometry: Name of fractal type used.
        level: Fractal recursion level used.
    """

    circuit: "QuantumCircuit"  # Forward reference
    metadata: CircuitMeta
    input_geometry: str = ""
    level: int = 0

    def to_qasm(self) -> str:
        """Export circuit to OpenQASM 2.0 string."""
        if QuantumCircuit is None:
            raise ImportError("Qiskit is required for circuit export")
        try:
            from qiskit import qasm2
            return qasm2.dumps(self.circuit)
        except (ImportError, AttributeError):
            # Fallback for older Qiskit versions
            return self.circuit.qasm()

    def to_draw(self, output: str = "text") -> str:
        """Render circuit diagram.

        Args:
            output: One of "text" (ASCII), "mpl" (matplotlib), "svg".

        Returns:
            String representation (text) or base64 encoded image data.
        """
        if QuantumCircuit is None:
            raise ImportError("Qiskit is required for circuit drawing")

        if output == "text":
            return self.circuit.draw()
        elif output in ("mpl", "svg"):
            return self.circuit.draw(output=output)
        else:
            raise ValueError(f"Unknown output format: {output}")

    def qubit_count(self) -> int:
        """Return number of qubits in circuit."""
        return self.circuit.num_qubits

    def gate_count(self) -> int:
        """Return total number of gates."""
        return self.circuit.size()

    def depth(self) -> int:
        """Return circuit depth (critical path)."""
        return self.circuit.depth()
