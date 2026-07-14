"""Geometric Resonance Engine — fractal geometry as physical-information architecture."""

__version__ = "0.1.0"

from gre.core.geometry import GeometryModel, Node, Edge, GeometryMeta
from gre.core.graph import GraphModel
from gre.core.circuit import CircuitModel, CircuitMeta
from gre.fractals.registry import FractalRegistry
from gre.simulation.quantum_walk import QuantumWalkSimulator, WalkResult
from gre.simulation.entropy import (
    shannon_entropy,
    von_neumann_entropy,
    topological_entropy,
    conditional_entropy_region,
)
from gre.engine import GeometricResonanceEngine

__all__ = [
    "__version__",
    # Core
    "GeometryModel", "Node", "Edge", "GeometryMeta",
    "GraphModel",
    "CircuitModel", "CircuitMeta",
    # Fractals
    "FractalRegistry",
    # Simulation
    "QuantumWalkSimulator", "WalkResult",
    "shannon_entropy", "von_neumann_entropy",
    "topological_entropy", "conditional_entropy_region",
    # Engine
    "GeometricResonanceEngine",
]
