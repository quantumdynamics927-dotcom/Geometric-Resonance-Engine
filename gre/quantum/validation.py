"""Hardware validation primitives.

Provides utilities for running circuits on real quantum hardware or
simulators and comparing results against classical baselines and
historical hardware runs.

This module bridges the gap between:
1. Classical simulation (established baselines)
2. Noisy simulation (Aer with noise model)
3. Real hardware execution (IBM Quantum, QuEra)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Callable
from enum import Enum
import numpy as np

try:
    from qiskit import QuantumCircuit
    from qiskit.providers import Backend
    from qiskit.providers.models import Qobj
    from qiskit.result import Result
    from qiskit.quantum_info import Statevector
except ImportError:
    QuantumCircuit = None
    Backend = None
    Result = None

from ..core.circuit import CircuitModel
from ..core.graph import GraphModel
from ..simulation.quantum_walk import WalkResult


class ExecutionBackend(Enum):
    """Known execution backends."""
    IBM_QASM_SIMULATOR = "ibmq_qasm_simulator"
    IBM_HARDWARE = "ibm_hardware"
    AER_SIMULATOR = "aer_simulator"
    AER_NOISY = "aer_noisy"
    QURA = "quera"
    LOCAL_STATEVECTOR = "local_statevector"


@dataclass
class ValidationConfig:
    """Configuration for hardware validation runs.

    Attributes:
        backend: Backend to execute on.
        shots: Number of measurement shots.
        seed: Random seed for reproducibility.
        transpile_optimization: Qiskit transpilation optimization level.
        apply_noise_model: Whether to apply a noise model (for AER_NOISY).
        noise_model_args: Arguments for noise model construction.
        max_results: Maximum number of results to collect.
        timeout: Timeout in seconds for execution.
    """

    backend: ExecutionBackend = ExecutionBackend.IBM_QASM_SIMULATOR
    shots: int = 2048
    seed: int = 42
    transpile_optimization: int = 1
    apply_noise_model: bool = False
    noise_model_args: Dict[str, Any] = field(default_factory=dict)
    max_results: int = 100
    timeout: int = 300


@dataclass
class ValidationResult:
    """Result of a hardware validation run.

    Attributes:
        experiment_id: Identifier for this validation run.
        backend: Backend used.
        shots: Number of shots executed.
        execution_time: Time taken to execute (seconds).
        counts: Measurement counts dictionary {state: count}.
        probabilities: Normalized probability distribution.
        classical_result: Reference classical simulation result.
        fidelity_vs_classical: Fidelity between hardware and classical results.
        kl_divergence: KL divergence between distributions.
        raw_result: Backend-specific raw result object.
    """

    experiment_id: str
    backend: str
    shots: int
    execution_time: float
    counts: Dict[str, int] = field(default_factory=dict)
    probabilities: np.ndarray = field(default_factory=lambda: np.array([]))
    classical_result: Optional[WalkResult] = None
    fidelity_vs_classical: Optional[float] = None
    kl_divergence: Optional[float] = None
    raw_result: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "backend": self.backend,
            "shots": self.shots,
            "execution_time": self.execution_time,
            "counts": self.counts,
            "fidelity_vs_classical": self.fidelity_vs_classical,
            "kl_divergence": self.kl_divergence,
        }


class HardwareValidationRunner:
    """Run quantum circuits on hardware or simulators and validate results.

    This runner provides a consistent interface for:
    1. Executing circuits on IBM Quantum, QuEra, or local simulators
    2. Comparing results against classical baselines
    3. Computing fidelity and divergence metrics
    4. Collecting results for analysis

    Usage:
        runner = HardwareValidationRunner(config=ValidationConfig(
            backend=ExecutionBackend.AER_SIMULATOR,
            shots=2048
        ))
        result = runner.run_circuit(
            circuit_model=circuit,
            classical_baseline=classical_walk_result,
            experiment_id="sierpinski-level3-01"
        )
    """

    def __init__(self, config: Optional[ValidationConfig] = None):
        self.config = config or ValidationConfig()
        self._backend = None

    def run_circuit(
        self,
        circuit_model: CircuitModel,
        classical_baseline: Optional[WalkResult] = None,
        experiment_id: str = "",
        **kwargs,
    ) -> ValidationResult:
        """Execute a circuit and compare against classical baseline.

        Args:
            circuit_model: CircuitModel to execute.
            classical_baseline: Optional WalkResult from classical simulation.
            experiment_id: Identifier for this validation run.
            **kwargs: Override config fields.

        Returns:
            ValidationResult with counts, probabilities, and metrics.
        """
        import time

        config = self.config
        for k, v in kwargs.items():
            setattr(config, k, v)

        experiment_id = experiment_id or f"exp-{int(time.time())}"

        # Select backend
        backend = self._get_backend(config.backend)

        # Transpile
        from qiskit import transpile
        transpiled = transpile(
            circuit_model.circuit,
            backend=backend,
            optimization_level=config.transpile_optimization,
        )

        # Execute
        start = time.time()
        raw_result = backend.run(transpiled, shots=config.shots, seed=config.seed)
        result = raw_result.result()
        execution_time = time.time() - start

        # Extract counts
        if hasattr(result, "get_counts"):
            counts = result.get_counts(transpiled)
        else:
            counts = {}

        # Compute probabilities
        total_shots = sum(counts.values()) or config.shots
        probabilities = np.zeros(2 ** circuit_model.metadata.qubit_count)
        for state, count in counts.items():
            idx = int(state.replace(" ", ""), 2) if isinstance(state, str) else state
            probabilities[idx] = count / total_shots

        # Compare to classical
        fidelity = None
        kl_div = None
        if classical_baseline is not None:
            fidelity = self._fidelity(probabilities, classical_baseline.probabilities)
            kl_div = self._kl_divergence(probabilities, classical_baseline.probabilities)

        return ValidationResult(
            experiment_id=experiment_id,
            backend=config.backend.value,
            shots=config.shots,
            execution_time=execution_time,
            counts=counts,
            probabilities=probabilities,
            classical_result=classical_baseline,
            fidelity_vs_classical=fidelity,
            kl_divergence=kl_div,
            raw_result=result,
        )

    def run_batch(
        self,
        circuits: List[CircuitModel],
        classical_baselines: Optional[List[WalkResult]] = None,
        experiment_prefix: str = "",
    ) -> List[ValidationResult]:
        """Execute multiple circuits in batch.

        Args:
            circuits: List of CircuitModel instances.
            classical_baselines: Optional list of WalkResult references.
            experiment_prefix: Prefix for experiment IDs.

        Returns:
            List of ValidationResult instances.
        """
        results = []
        for i, circuit in enumerate(circuits):
            baseline = None
            if classical_baselines and i < len(classical_baselines):
                baseline = classical_baselines[i]

            result = self.run_circuit(
                circuit_model=circuit,
                classical_baseline=baseline,
                experiment_id=f"{experiment_prefix}-{i:03d}",
            )
            results.append(result)

        return results

    def _get_backend(self, backend_type: ExecutionBackend):
        """Get a Qiskit backend for the given type."""
        if backend_type == ExecutionBackend.IBM_QASM_SIMULATOR:
            from qiskit.providers.basic_provider import BasicProvider
            provider = BasicProvider()
            return provider.get_backend("statevector_simulator")

        elif backend_type == ExecutionBackend.AER_SIMULATOR:
            from qiskit_aer import Aer
            return Aer.get_backend("aer_simulator")

        elif backend_type == ExecutionBackend.AER_NOISY:
            from qiskit_aer import Aer
            return Aer.get_backend("aer_simulator")

        elif backend_type == ExecutionBackend.LOCAL_STATEVECTOR:
            from qiskit.providers.basic_provider import BasicProvider
            provider = BasicProvider()
            return provider.get_backend("statevector_simulator")

        else:
            raise ValueError(f"Unsupported backend type: {backend_type}")

    @staticmethod
    def _fidelity(p: np.ndarray, q: np.ndarray) -> float:
        """Compute classical fidelity F(p, q) = Σ √(p_i q_i)."""
        p = np.asarray(p, dtype=np.float64)
        q = np.asarray(q, dtype=np.float64)
        p = p / np.sum(p)
        q = q / np.sum(q)
        return float(np.sum(np.sqrt(p * q)))

    @staticmethod
    def _kl_divergence(p: np.ndarray, q: np.ndarray) -> float:
        """Compute KL divergence D(p || q) = Σ p_i log(p_i / q_i)."""
        p = np.asarray(p, dtype=np.float64)
        q = np.asarray(q, dtype=np.float64)
        p = p / np.sum(p)
        q = q / np.sum(q)

        # Avoid log(0)
        mask = (p > 1e-15) & (q > 1e-15)
        return float(np.sum(p[mask] * np.log(p[mask] / q[mask])))

    @staticmethod
    def _total_variation_distance(p: np.ndarray, q: np.ndarray) -> float:
        """Compute total variation distance: (1/2) Σ |p_i - q_i|."""
        p = np.asarray(p, dtype=np.float64)
        q = np.asarray(q, dtype=np.float64)
        return float(0.5 * np.sum(np.abs(p - q)))

    def compare_to_historical(
        self,
        validation_result: ValidationResult,
        historical_runs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Compare a validation result against historical hardware runs.

        Args:
            validation_result: Current validation result.
            historical_runs: List of historical run records.

        Returns:
            Dict with comparison summary.
        """
        if not historical_runs:
            return {"match_count": 0, "message": "No historical runs provided"}

        # Extract fidelity from historical runs
        historical_fidelities = [
            r.get("fidelity") for r in historical_runs
            if r.get("fidelity") is not None
        ]

        if not historical_fidelities:
            return {
                "validation_fidelity": validation_result.fidelity_vs_classical,
                "historical_count": len(historical_runs),
                "message": "No fidelity data in historical runs",
            }

        avg_historical = sum(historical_fidelities) / len(historical_fidelities)

        return {
            "validation_fidelity": validation_result.fidelity_vs_classical,
            "historical_avg_fidelity": avg_historical,
            "historical_min_fidelity": min(historical_fidelities),
            "historical_max_fidelity": max(historical_fidelities),
            "improvement_vs_historical": (
                validation_result.fidelity_vs_classical - avg_historical
                if validation_result.fidelity_vs_classical is not None
                else None
            ),
        }
