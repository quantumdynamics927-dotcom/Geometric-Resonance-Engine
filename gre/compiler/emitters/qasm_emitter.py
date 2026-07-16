from ..ir import CompilationResult
from typing import Optional


class QASMEmitter:
    """Emit OpenQASM 2.0 string from CompilationResult.

    Supports both Qiskit 1.x (circuit.qasm()) and Qiskit 2.x (qiskit.qasm2.dumps).
    """

    def emit(self, result: CompilationResult, strategy: str = "staggered") -> Optional[str]:
        """Return OpenQASM 2.0 string, or None if QASM export fails."""
        qc = None
        try:
            from .qiskit_emitter import QiskitCircuitEmitter
            emitter = QiskitCircuitEmitter()
            qc = emitter.emit(result, strategy)
        except Exception:
            pass

        if qc is None:
            return None

        try:
            # Qiskit 2.x
            import qiskit.qasm2 as qasm2
            return qasm2.dumps(qc)
        except (ImportError, AttributeError):
            pass

        try:
            # Qiskit 1.x fallback
            return qc.qasm()  # type: ignore[attr-defined]
        except Exception:
            return None
