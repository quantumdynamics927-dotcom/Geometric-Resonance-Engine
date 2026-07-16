from ..ir import CompilationResult
from typing import Optional


class QiskitCircuitEmitter:
    """Emit QuantumCircuit from CompilationResult via QuantumWalkCircuitBuilder.

    Wraps the existing QuantumWalkCircuitBuilder from gre/quantum/walk_circuit.py.
    Falls back gracefully when Qiskit is unavailable.
    """

    def emit(self, result: CompilationResult, strategy: str = "staggered") -> "QuantumCircuit":
        """Build and return a Qiskit QuantumCircuit.

        strategy: one of the computed walk strategies in result.walk_results.
        Returns None if strategy not computed or Qiskit unavailable.
        """
        try:
            from qiskit import QuantumCircuit
        except ImportError:
            return None

        if strategy not in result.walk_results:
            # Try first available strategy
            strategy = next(iter(result.walk_results.keys()), None)
            if strategy is None:
                return None

        strategy_result = result.walk_results[strategy]

        # If circuit was already built during compilation, return it
        if strategy_result.circuit is not None:
            return strategy_result.circuit.circuit

        # Fall back: build fresh circuit using QuantumWalkCircuitBuilder
        try:
            from ...quantum.walk_circuit import QuantumWalkCircuitBuilder, WalkCircuitConfig
            builder = QuantumWalkCircuitBuilder()
            config = WalkCircuitConfig(
                walk_model=strategy,
                coin_type="hadamard",
                encoding="one_hot",
                add_measurements=False,
                record_state=False,
            )
            circuit_model = builder.build(
                result.graph,
                steps=result.walk_strategies_computed.index(strategy) + 5,
                initial_node=0,
                config=config,
            )
            return circuit_model.circuit
        except Exception:
            # Fall back to UnitaryGate approach for staggered
            if strategy == "staggered":
                return self._build_unitary_fallback(result)
            return None

    def _build_unitary_fallback(self, result: CompilationResult):
        """Build circuit using exp(-i·π/2·L_sym) as UnitaryGate."""
        try:
            from qiskit import QuantumCircuit
            from qiskit.circuit.library import UnitaryGate
        except ImportError:
            return None

        n = result.graph.adjacency.shape[0]
        qc = QuantumCircuit(n)

        # Compute normalized Laplacian
        adj = result.graph.adjacency
        deg = np.diag(np.array(adj.sum(axis=1)).flatten())
        import numpy as np
        D_inv_sqrt = np.diag(1.0 / (np.sqrt(np.diag(deg)) + 1e-12))
        L_sym = np.eye(n) - D_inv_sqrt @ adj @ D_inv_sqrt

        # Walk unitary: exp(-i * π/2 * L_sym)
        walk_unitary = scipy.linalg.expm(-1j * np.pi / 2 * L_sym)
        qc.append(UnitaryGate(walk_unitary), qc.qubits)
        return qc
