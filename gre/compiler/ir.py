from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from ..core.circuit import CircuitModel
from ..core.geometry import GeometryModel
from ..core.graph import GraphModel
from ..simulation.quantum_walk import WalkResult


class WalkStrategy(Enum):
    COINED = "coined"
    STAGGERED = "staggered"
    QUTRIT = "qutrit"
    STAGGERED_CONTINUOUS = "staggered_continuous"


@dataclass
class SymmetrySector:
    coloring: np.ndarray  # shape (N,) — greedy 3-color assignment 0/1/2
    sector_labels: List[str]  # e.g. ["boundary", "interior", "vertex_centered"]
    sector_counts: Dict[str, int]  # count per sector
    automorphism_invariant: bool  # True if D3 invariant
    description: str


@dataclass
class MultiscalePartition:
    level: int
    clusters: List[Set[int]]  # node IDs per cluster
    inter_cluster_edges: List[Tuple[int, int]]
    cluster_centers: List[int]
    partition_matrix: np.ndarray  # (k, N) soft or (N,) hard


@dataclass
class ResonanceDescriptor:
    eigenvalues: np.ndarray
    spectral_moments: Dict[str, float]  # mean, variance, skewness, kurtosis
    spectral_gap: float
    eigenvalue_spacing_ratio: float
    resonance_frequency: float
    resonance_coupling: float
    num_resonance_bands: int
    fixed_point_angles: np.ndarray
    golden_ratio_ratio: float
    degree_distribution: np.ndarray
    average_degree: float

    def to_fingerprint(self) -> str:
        data = {
            "spectral_gap": round(self.spectral_gap, 6),
            "eigenvalue_spacing_ratio": round(self.eigenvalue_spacing_ratio, 6),
            "resonance_frequency": round(self.resonance_frequency, 6),
            "resonance_coupling": round(self.resonance_coupling, 6),
            "num_resonance_bands": int(self.num_resonance_bands),
            "average_degree": round(self.average_degree, 6),
            "golden_ratio_ratio": round(self.golden_ratio_ratio, 6),
        }
        fingerprint = hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()
        return fingerprint[:32]


@dataclass
class AttractorSignature:
    entropy_trajectory: str  # stable/increasing/decreasing/oscillating
    entropy_rate: float
    participation_ratio_final: float
    participation_ratio_trend: str  # localizing/delocalizing/stable/oscillating
    transfer_class: str  # perfect(>0.95)/partial(0.3-0.95)/none(<0.3)
    optimal_transfer_steps: Optional[int]
    eigenstate_correlation: Optional[float]
    attractor_label: str  # compound: f"{entropy_trajectory}_{participation_ratio_trend}_{transfer_class}"

    def __str__(self) -> str:
        return self.attractor_label


@dataclass
class WalkStrategyResult:
    strategy: WalkStrategy
    walk_result: WalkResult
    circuit: Optional[CircuitModel]
    attractor_signature: AttractorSignature
    resonance_descriptor: ResonanceDescriptor


@dataclass
class GeometryCompilerConfig:
    emit_circuits: bool = True
    compute_symmetry: bool = True
    compute_multiscale: bool = True
    corpus_path: Optional[str] = None
    walk_steps: int = 20
    initial_node: int = 0
    strategies: Optional[List[str]] = None  # None = all


@dataclass
class CompilationResult:
    source_type: str
    source_id: str
    geometry: GeometryModel
    graph: GraphModel
    symmetry_sector: Optional[SymmetrySector]
    multiscale_partition: Optional[MultiscalePartition]
    walk_results: Dict[str, WalkStrategyResult]
    resonance_descriptor: ResonanceDescriptor
    attractor_signature: AttractorSignature
    compile_time_ms: float
    emit_circuits: bool
    walk_strategies_computed: List[str]
    _corpus: Any = field(default=None, compare=False)

    def compare_to_corpus(self, corpus: Any, tolerance: float = 0.1) -> Any:
        from .comparison import CorpusComparisonView

        return CorpusComparisonView(self, corpus, tolerance)

    def emit(self, target: str = "qiskit", **kwargs: Any) -> Any:
        from .emitters import (
            CircuitModelEmitter,
            QASMEmitter,
            QiskitCircuitEmitter,
        )

        if target == "qiskit":
            return QiskitCircuitEmitter().emit(self, **kwargs)
        elif target == "qasm":
            return QASMEmitter().emit(self, **kwargs)
        elif target == "circuit_model":
            return CircuitModelEmitter().emit(self, **kwargs)
        elif target == "all":
            return {
                "qiskit": QiskitCircuitEmitter().emit(self, **kwargs),
                "qasm": QASMEmitter().emit(self, **kwargs),
                "circuit_model": CircuitModelEmitter().emit(self, **kwargs),
            }
        else:
            raise ValueError(f"Unknown emit target: {target}")
