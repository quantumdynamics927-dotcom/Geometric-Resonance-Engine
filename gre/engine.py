"""Top-level Geometric Resonance Engine API."""

from typing import Optional, Dict, Any

import numpy as np

from .core.geometry import GeometryModel
from .core.graph import GraphModel
from .core.circuit import CircuitModel
from .fractals.registry import FractalRegistry
from .simulation.quantum_walk import QuantumWalkSimulator, WalkResult
from .simulation.entropy import shannon_entropy, von_neumann_entropy, topological_entropy


class GeometricResonanceEngine:
    """Main entry point for GRE.

    Provides a unified interface to the full geometry → graph → simulation
    → circuit → hardware pipeline.

    Example:
        gre = GeometricResonanceEngine(level=5)

        geometry = gre.generate("sierpinski", route="ifs")
        graph = gre.derive_graph(geometry)
        result = gre.simulate.staggered_walk(graph, steps=20)
        circuit = gre.quantum.map_to_circuit(graph, walk_steps=20)
        stability = gre.metrics.stability_score(graph)
    """

    def __init__(self, level: int = 3):
        """Initialize GRE at a default recursion level.

        Args:
            level: Default fractal recursion level (overridden per-call as needed).
        """
        self.default_level = level

    # -------------------------------------------------------------------------
    # Fractal generation
    # -------------------------------------------------------------------------

    def generate(
        self,
        fractal: str = "sierpinski",
        level: Optional[int] = None,
        route: str = "ifs",
        **kwargs
    ) -> GeometryModel:
        """Generate a fractal geometry.

        Args:
            fractal: Fractal type name (default "sierpinski").
            level: Recursion depth (defaults to self.default_level).
            route: Mathematical generation route.
            **kwargs: Additional arguments to the generator.

        Returns:
            GeometryModel for the fractal at this level.
        """
        level = level if level is not None else self.default_level
        return FractalRegistry.create(fractal, level=level, route=route, **kwargs)

    # -------------------------------------------------------------------------
    # Graph derivation
    # -------------------------------------------------------------------------

    def derive_graph(self, geometry: GeometryModel) -> GraphModel:
        """Derive a coupling graph from fractal geometry.

        Args:
            geometry: GeometryModel from generate().

        Returns:
            GraphModel with adjacency, Laplacian, and eigenpairs.
        """
        return GraphModel.from_geometry(geometry)

    # -------------------------------------------------------------------------
    # Simulation
    # -------------------------------------------------------------------------

    @property
    def simulate(self) -> "SimulationFacade":
        """Facade for simulation operations."""
        return SimulationFacade(self)

    def quantum_walk(
        self,
        graph: GraphModel,
        steps: int,
        initial_node: int = 0,
        model: str = "staggered"
    ) -> WalkResult:
        """Simulate a quantum walk on the graph.

        Args:
            graph: GraphModel to walk on.
            steps: Number of walk steps.
            initial_node: Starting node index.
            model: "staggered" (default) or "coined".

        Returns:
            WalkResult with probability distribution and metrics.
        """
        simulator = QuantumWalkSimulator(graph)
        if model == "staggered":
            return simulator.staggered_walk(steps=steps, initial_node=initial_node)
        elif model == "coined":
            return simulator.coined_walk(steps=steps, initial_node=initial_node)
        else:
            raise ValueError(f"Unknown walk model: {model}")

    # -------------------------------------------------------------------------
    # Quantum circuit mapping (stub — full implementation in quantum module)
    # -------------------------------------------------------------------------

    @property
    def quantum(self) -> "QuantumFacade":
        """Facade for quantum circuit operations."""
        return QuantumFacade(self)

    # -------------------------------------------------------------------------
    # Metrics (stub — full implementation in metrics module)
    # -------------------------------------------------------------------------

    @property
    def metrics(self) -> "MetricsFacade":
        """Facade for scoring metrics."""
        return MetricsFacade(self)


class SimulationFacade:
    """Facade for simulation operations."""

    def __init__(self, engine: GeometricResonanceEngine):
        self._engine = engine

    def staggered_walk(
        self,
        graph: GraphModel,
        steps: int,
        initial_node: int = 0
    ) -> WalkResult:
        """Simulate a staggered quantum walk."""
        return self._engine.quantum_walk(graph, steps, initial_node, model="staggered")

    def coined_walk(
        self,
        graph: GraphModel,
        steps: int,
        initial_node: int = 0,
        coin: str = "grover"
    ) -> WalkResult:
        """Simulate a coined quantum walk."""
        simulator = QuantumWalkSimulator(graph)
        return simulator.coined_walk(steps=steps, initial_node=initial_node, coin=coin)

    def wave_propagation(
        self,
        graph: GraphModel,
        initial_node: int,
        steps: int,
        damping: float = 0.0
    ) -> WalkResult:
        """Simulate classical wave propagation."""
        simulator = QuantumWalkSimulator(graph)
        probs = simulator.wave_propagation(initial_node, steps, damping)
        import numpy as np
        final = probs[-1]
        total = np.sum(final)
        if total < 1e-15:
            final = np.ones_like(final) / len(final)
            total = 1.0
        return WalkResult(
            probabilities=final / total,
            position_entropy=shannon_entropy(final),
            state_vector_history=probs,
            participation_ratio=float(
                total ** 2 / np.sum(final ** 2)
            ),
        )


class QuantumFacade:
    """Facade for quantum circuit operations.

    Wraps gre/quantum/mapper.py and gre/quantum/walk_circuit.py.
    """

    def __init__(self, engine: GeometricResonanceEngine):
        self._engine = engine
        self._mapper_config = None  # Lazy-loaded MapperConfig

    @property
    def mapper_config(self):
        """Lazy-load MapperConfig."""
        if self._mapper_config is None:
            from .quantum.mapper import MapperConfig
            self._mapper_config = MapperConfig()
        return self._mapper_config

    def map_to_circuit(
        self,
        graph: GraphModel,
        walk_steps: int,
        initial_node: int = 0,
        encoding: str = "qubit",
        walk_model: str = "staggered",
    ) -> CircuitModel:
        """Map a graph and walk to a quantum circuit.

        Uses GraphCircuitMapper for one-hot/binary/amplitude encoding,
        or QuantumWalkCircuitBuilder for coined/staggered walk circuits.

        Args:
            graph: GraphModel to encode.
            walk_steps: Number of quantum walk steps.
            initial_node: Starting node index.
            encoding: "one_hot", "binary", or "amplitude".
            walk_model: "staggered" or "coined".

        Returns:
            CircuitModel wrapping a Qiskit QuantumCircuit.
        """
        from .quantum.mapper import GraphCircuitMapper, MapperConfig
        from .quantum.walk_circuit import QuantumWalkCircuitBuilder, WalkCircuitConfig

        if walk_model == "staggered":
            # Use dedicated walk circuit builder
            builder = QuantumWalkCircuitBuilder()
            config = WalkCircuitConfig(
                walk_model="staggered",
                encoding=encoding,
                add_measurements=True,
            )
            return builder.build(graph, steps=walk_steps, initial_node=initial_node, config=config)
        else:
            # Use general mapper
            mapper = GraphCircuitMapper(
                MapperConfig(encoding=encoding, add_measurements=True)
            )
            return mapper.graph_to_circuit(
                graph, walk_steps=walk_steps, initial_node=initial_node
            )


class MetricsFacade:
    """Facade for scoring metrics.

    Full implementation lives in gre/metrics/.
    """

    def __init__(self, engine: GeometricResonanceEngine):
        self._engine = engine

    def stability_score(self, graph: GraphModel) -> float:
        """Compute stability score = spectral gap λ₂ of Laplacian.

        Larger spectral gap → more stable oscillation, less prone to decoherence.
        """
        return float(graph.spectral_gap())

    def entropy_quality_score(
        self,
        shannon_ent: float,
        n: int
    ) -> float:
        """How close the entropy is to the maximum (uniform) entropy.

        Score = H / H_max, in [0, 1].
        """
        H_max = shannon_entropy(np.ones(n) / n)
        return float(shannon_ent / H_max) if H_max > 0 else 0.0

    def localization_score(self, probs: np.ndarray) -> float:
        """Participation ratio normalized: PR / N.

        1.0 = fully delocalized (uniform).
        → 0 = fully localized (single peak).
        """
        n = len(probs)
        pr = float(np.sum(probs) ** 2 / np.sum(probs ** 2))
        return pr / n if n > 0 else 0.0


# Module-level convenience
from .core.geometry import GeometryModel as Geometry
from .core.graph import GraphModel as Graph
from .core.circuit import CircuitModel as Circuit

__all__ = [
    "GeometricResonanceEngine",
    "Geometry", "Graph", "Circuit",
    "GeometryModel", "GraphModel", "CircuitModel",
    "QuantumWalkSimulator", "WalkResult",
    "shannon_entropy", "von_neumann_entropy", "topological_entropy",
    "FractalRegistry",
]
