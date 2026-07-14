"""Typed schemas for research artifacts.

These are the canonical record types for importing, storing, and querying
prior hardware runs, Sierpinski experiments, and calibration snapshots
from QSG, Sierpinski, and other prior projects.

Every record carries a ProvenanceSidecar that tracks origin, transformation
chain, and sensitivity classification.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional

from .provenance import ProvenanceSidecar


class ExperimentTag(Enum):
    """Known hypothesis tags for classifying experiments."""
    SIERPINSKI_DEPTH_INVARIANT = "sierpinski_depth_invariant"
    FIXED_POINT_1_OVER_PHI = "fixed_point_1_over_phi"
    STRUCTURAL_ENCODING = "structural_encoding"
    QUATRIT_MAPPING = "qutrit_mapping"
    LC_RESONATOR = "lc_resonator"
    MULTIBAND_RESONANCE = "multiband_resonance"
    PLASMONIC_REDSHIFT = "plasmonic_redshift"
    QUANTUM_ISING_CRITICAL = "quantum_ising_critical"
    ENTROPY_EXTRACTION = "entropy_extraction"
    DECOHERENCE_FREE_SUBSPACE = "decoherence_free_subspace"
    GRAPH_STATE_TRANSFER = "graph_state_transfer"
    OTHER = "other"


class CircuitFamily(Enum):
    """Circuit families used in prior experiments."""
    FRACTAL_WALK = "fractal_walk"
    STAGGERED_WALK = "staggered_walk"
    COINED_WALK = "coined_walk"
    QAOA_STYLE = "qaoa_style"
    VARIATIONAL = "variational"
    GATE_BASED = "gate_based"
    MEASUREMENT_BASED = "measurement_based"
    UNKNOWN = "unknown"


class EvidenceClass(Enum):
    """Classification of artifact by evidence type.

    Historical real artifacts are observed data from actual executions.
    Synthetic seed artifacts are generated reference circuits or structures.
    Derived summary artifacts are post-hoc analyses of other artifacts.
    """
    HISTORICAL_REAL = "historical_real"
    SYNTHETIC_SEED = "synthetic_seed"
    DERIVED_SUMMARY = "derived_summary"


class ValidationTier(Enum):
    """Maturity level of an artifact's metrics and processing.

    raw:                Raw output directly from hardware/software — unprocessed.
    normalized:         Field names, types, and formats standardized.
    benchmarked:        Compared against theoretical predictions or baselines.
    measured:           Physically measured with instruments; highest confidence.
    """
    RAW = "raw"
    NORMALIZED = "normalized"
    BENCHMARKED = "benchmarked"
    MEASURED = "measured"


class BackendGeneration(Enum):
    """IBM Quantum hardware generation / series.

    Eagle:     65-qubit H1-series (2021)
    Heron:     100+ qubit Fez/Kingston (2023-2026)
    Falcon:    27-qubit Casablanca-era (2020-2021)
    Eagle_r3:  127+ qubit IBM Quantum System One (2023)
    Simulator: QASM and Aer simulators
    Unknown:   Cannot be determined from available data
    """
    IBM_EAGLE = "ibm_eagle"
    IBM_HERRON = "ibm_herron"
    IBM_FALCON = "ibm_falcon"
    IBM_EAGLE_R3 = "ibm_eagle_r3"
    IBM_QUERA = "ibm_quera"
    SIMULATOR = "simulator"
    UNKNOWN = "unknown"


class CalibrationCompleteness(Enum):
    """How complete the physical calibration data is for a calibration snapshot.

    physical:   Full T1, T2, readout, gate errors, frequencies present.
    metadata:   Only timestamp, backend, and configuration metadata.
    absent:     No calibration data available.
    """
    PHYSICAL = "physical"
    METADATA = "metadata"
    ABSENT = "absent"


class BackendName(Enum):
    """Known quantum hardware backend identifiers."""
    IBM_QASM_SIMULATOR = "ibmq_qasm_simulator"
    IBM_PERTH = "ibmq_perth"
    IBM_KANKAN = "ibmq_kankan"
    IBM_GUADALUPE = "ibmq_guadalupe"
    IBM_MANILA = "ibmq_manila"
    IBM_LIMA = "ibmq_lima"
    IBM_QUERA = "quera_ae"
    LOCAL_AER = "aer_simulator"
    OTHER = "other"


@dataclass
class ExperimentMetadata:
    """Metadata common to all experiment records.

    Attributes:
        experiment_id: Unique identifier for this run (e.g., "qsg-run-042").
        project: Source project name (e.g., "qsg", "sierpinski", "tmt").
        date: ISO-8601 date string when the run was executed.
        hypothesis_tag: Primary hypothesis this run was testing.
        circuit_family: Circuit family used.
        notes: Free-text notes on what was observed or anomalies.
    """

    experiment_id: str
    project: str
    date: str  # ISO-8601
    hypothesis_tag: ExperimentTag
    circuit_family: CircuitFamily
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "project": self.project,
            "date": self.date,
            "hypothesis_tag": self.hypothesis_tag.value,
            "circuit_family": self.circuit_family.value,
            "notes": self.notes,
        }


@dataclass
class HardwareRunRecord:
    """Record of a single execution on quantum hardware or simulator.

    This is the primary record type for IBM Quantum, QuEra, and local
    Aer simulator runs. It normalizes results from diverse backends into
    a consistent schema.

    Attributes:
        metadata: ExperimentMetadata for this run.
        backend: BackendName or raw string identifier.
        qubit_count: Number of physical qubits used.
        depth: Circuit depth (gate count along critical path).
        shots: Number of measurement shots (0 for exact simulation).
        gate_counts: Dict of gate type → count.
        calibration_snapshot_id: ID linking to nearest CalibrationSnapshot.
        expected_metrics: List of metric names this run was expected to produce.
        observed_metrics: Dict of metric name → observed value.
        fidelity: Overall fidelity estimate if computed.
        phi_deviation: Deviation from 1/φ ≈ 0.618 if applicable.
        sierpinski_score: Sierpinski-specific score if computed.
        raw_data_ref: Path or reference to raw output data.
        provenance: ProvenanceSidecar tracking origin and transformation.
    """

    metadata: ExperimentMetadata
    backend: str  # BackendName.value or raw string
    qubit_count: int
    depth: int
    shots: int
    gate_counts: Dict[str, int] = field(default_factory=dict)
    calibration_snapshot_id: Optional[str] = None
    expected_metrics: List[str] = field(default_factory=list)
    observed_metrics: Dict[str, float] = field(default_factory=dict)
    fidelity: Optional[float] = None
    phi_deviation: Optional[float] = None
    sierpinski_score: Optional[float] = None
    raw_data_ref: str = ""
    is_synthetic: bool = False  # True = generated/seed artifact; False = historical_real
    confidence_tier: str = "inferred"  # "measured" | "inferred" | "extrapolated" | "unvalidated"
    evidence_class: str = "historical_real"  # "historical_real" | "synthetic_seed" | "derived_summary"
    validation_tier: str = "normalized"  # "raw" | "normalized" | "benchmarked" | "measured"
    backend_generation: str = "unknown"  # BackendGeneration.value
    provenance: ProvenanceSidecar = field(default_factory=ProvenanceSidecar)

    def to_dict(self) -> Dict[str, Any]:
        base = self.metadata.to_dict()
        base.update({
            "backend": self.backend,
            "qubit_count": self.qubit_count,
            "depth": self.depth,
            "shots": self.shots,
            "gate_counts": self.gate_counts,
            "calibration_snapshot_id": self.calibration_snapshot_id,
            "expected_metrics": self.expected_metrics,
            "observed_metrics": self.observed_metrics,
            "fidelity": self.fidelity,
            "phi_deviation": self.phi_deviation,
            "sierpinski_score": self.sierpinski_score,
            "raw_data_ref": self.raw_data_ref,
            "is_synthetic": self.is_synthetic,
            "confidence_tier": self.confidence_tier,
            "evidence_class": self.evidence_class,
            "validation_tier": self.validation_tier,
            "backend_generation": self.backend_generation,
            "provenance": self.provenance.to_dict(),
        })
        return base

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "HardwareRunRecord":
        meta = ExperimentMetadata(
            experiment_id=d["experiment_id"],
            project=d["project"],
            date=d["date"],
            hypothesis_tag=ExperimentTag(d.get("hypothesis_tag", "other")),
            circuit_family=CircuitFamily(d.get("circuit_family", "unknown")),
            notes=d.get("notes", ""),
        )
        provenance = ProvenanceSidecar.from_dict(d.get("provenance", {}))
        return cls(
            metadata=meta,
            backend=d["backend"],
            qubit_count=d["qubit_count"],
            depth=d["depth"],
            shots=d["shots"],
            gate_counts=d.get("gate_counts", {}),
            calibration_snapshot_id=d.get("calibration_snapshot_id"),
            expected_metrics=d.get("expected_metrics", []),
            observed_metrics=d.get("observed_metrics", {}),
            fidelity=d.get("fidelity"),
            phi_deviation=d.get("phi_deviation"),
            sierpinski_score=d.get("sierpinski_score"),
            raw_data_ref=d.get("raw_data_ref", ""),
            is_synthetic=d.get("is_synthetic", False),
            confidence_tier=d.get("confidence_tier", "inferred"),
            evidence_class=d.get("evidence_class", "historical_real"),
            validation_tier=d.get("validation_tier", "normalized"),
            backend_generation=d.get("backend_generation", "unknown"),
            provenance=provenance,
        )

    def matches_filter(
        self,
        depth: Optional[int] = None,
        backend: Optional[str] = None,
        project: Optional[str] = None,
        hypothesis_tag: Optional[ExperimentTag] = None,
    ) -> bool:
        """Check if this record matches the given filter criteria."""
        if depth is not None and self.metadata.experiment_id.split("-")[-1] != str(depth):
            pass  # depth is not in experiment_id; check circuit depth
        if depth is not None and self.depth != depth:
            return False
        if backend is not None and self.backend != backend:
            return False
        if project is not None and self.metadata.project != project:
            return False
        if hypothesis_tag is not None and self.metadata.hypothesis_tag != hypothesis_tag:
            return False
        return True


@dataclass
class SierpinskiExperimentRecord:
    """Record for a Sierpinski-specific experiment.

    Extends HardwareRunRecord with Sierpinski-specific fields for
    structural encoding, depth-invariant behavior, and fixed-point analysis.

    Attributes:
        hardware_record: The underlying HardwareRunRecord.
        recursion_level: Sierpinski recursion level n (3^n triangles).
        hausdorff_dimension: Expected Hausdorff dimension (log₂(3) ≈ 1.585).
        structural_encoding_depth: Depth at which structural encoding was tested.
        depth_invariant_fixed_point: Observed fixed-point value (expected ≈ 1/φ).
        depth_invariant_confidence: Confidence level of fixed-point claim.
        route: Mathematical route used (ifs, pascal_mod2, rule90, hanoi, etc.).
        void_encoding_used: Whether void region was used as decoherence-free subspace.
        fractal_graph_nodes: Number of nodes in the fractal graph.
        fractal_graph_edges: Number of edges in the fractal graph.
    """

    hardware_record: HardwareRunRecord
    recursion_level: int = 0
    hausdorff_dimension: float = 1.5849625  # log2(3)
    structural_encoding_depth: int = 0
    depth_invariant_fixed_point: Optional[float] = None
    depth_invariant_confidence: Optional[float] = None
    route: str = "ifs"
    void_encoding_used: bool = False
    fractal_graph_nodes: int = 0
    fractal_graph_edges: int = 0

    def to_dict(self) -> Dict[str, Any]:
        base = self.hardware_record.to_dict()
        base.update({
            "recursion_level": self.recursion_level,
            "hausdorff_dimension": self.hausdorff_dimension,
            "structural_encoding_depth": self.structural_encoding_depth,
            "depth_invariant_fixed_point": self.depth_invariant_fixed_point,
            "depth_invariant_confidence": self.depth_invariant_confidence,
            "route": self.route,
            "void_encoding_used": self.void_encoding_used,
            "fractal_graph_nodes": self.fractal_graph_nodes,
            "fractal_graph_edges": self.fractal_graph_edges,
        })
        return base

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SierpinskiExperimentRecord":
        hw = HardwareRunRecord.from_dict(d)
        return cls(
            hardware_record=hw,
            recursion_level=d.get("recursion_level", 0),
            hausdorff_dimension=d.get("hausdorff_dimension", 1.5849625),
            structural_encoding_depth=d.get("structural_encoding_depth", 0),
            depth_invariant_fixed_point=d.get("depth_invariant_fixed_point"),
            depth_invariant_confidence=d.get("depth_invariant_confidence"),
            route=d.get("route", "ifs"),
            void_encoding_used=d.get("void_encoding_used", False),
            fractal_graph_nodes=d.get("fractal_graph_nodes", 0),
            fractal_graph_edges=d.get("fractal_graph_edges", 0),
        )

    @property
    def experiment_id(self) -> str:
        return self.hardware_record.metadata.experiment_id

    @property
    def project(self) -> str:
        return self.hardware_record.metadata.project


@dataclass
class CalibrationSnapshot:
    """Record for a calibration context snapshot.

    Calibration snapshots capture the quantum hardware state at the time
    of a hardware run, enabling reproducibility and noise characterization.

    Attributes:
        snapshot_id: Unique identifier for this calibration snapshot.
        backend: BackendName.value this calibration applies to.
        timestamp: ISO-8601 timestamp of calibration.
        t1_times: Dict qubit_id → T1 relaxation time in microseconds.
        t2_times: Dict qubit_id → T2 dephasing time in microseconds.
        readout_errors: Dict qubit_id → readout error rate.
        gate_errors: Dict gate_name → average gate error rate.
        qubit_freqs: Dict qubit_id → frequency in GHz.
        readouts: Dict qubit_id → readout assignment fidelity.
        connectivity: List of (control_qubit, target_qubit) couples for CNOT.
        raw_calibration_ref: Path or reference to raw calibration data.
        provenance: ProvenanceSidecar.
    """

    snapshot_id: str
    backend: str
    timestamp: str  # ISO-8601
    t1_times: Dict[str, float] = field(default_factory=dict)
    t2_times: Dict[str, float] = field(default_factory=dict)
    readout_errors: Dict[str, float] = field(default_factory=dict)
    gate_errors: Dict[str, float] = field(default_factory=dict)
    qubit_freqs: Dict[str, float] = field(default_factory=dict)
    readouts: Dict[str, float] = field(default_factory=dict)
    connectivity: List[tuple] = field(default_factory=list)
    raw_calibration_ref: str = ""
    is_synthetic: bool = False
    confidence_tier: str = "measured"
    calibration_completeness: str = "physical"  # "physical" | "metadata" | "absent"
    provenance: ProvenanceSidecar = field(default_factory=ProvenanceSidecar)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "backend": self.backend,
            "timestamp": self.timestamp,
            "t1_times": self.t1_times,
            "t2_times": self.t2_times,
            "readout_errors": self.readout_errors,
            "gate_errors": self.gate_errors,
            "qubit_freqs": self.qubit_freqs,
            "readouts": self.readouts,
            "connectivity": [list(c) for c in self.connectivity],
            "raw_calibration_ref": self.raw_calibration_ref,
            "is_synthetic": self.is_synthetic,
            "confidence_tier": self.confidence_tier,
            "calibration_completeness": self.calibration_completeness,
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CalibrationSnapshot":
        provenance = ProvenanceSidecar.from_dict(d.get("provenance", {}))
        return cls(
            snapshot_id=d["snapshot_id"],
            backend=d["backend"],
            timestamp=d["timestamp"],
            t1_times=d.get("t1_times", {}),
            t2_times=d.get("t2_times", {}),
            readout_errors=d.get("readout_errors", {}),
            gate_errors=d.get("gate_errors", {}),
            qubit_freqs=d.get("qubit_freqs", {}),
            readouts=d.get("readouts", {}),
            connectivity=[tuple(c) for c in d.get("connectivity", [])],
            raw_calibration_ref=d.get("raw_calibration_ref", ""),
            is_synthetic=d.get("is_synthetic", False),
            confidence_tier=d.get("confidence_tier", "measured"),
            calibration_completeness=d.get("calibration_completeness", "physical"),
            provenance=provenance,
        )


@dataclass
class ArtifactDescriptor:
    """Lightweight descriptor for an artifact referenced in a record.

    Used to link records to their source files without duplicating
    full artifact data.

    Attributes:
        artifact_id: Unique ID for this artifact.
        artifact_type: Type label (e.g., "csv", "json", "qasm", "png").
        source_project: Project this was imported from.
        source_path: Original path within source project.
        source_commit: Git commit hash in source project at import time.
        sensitivity: "public", "internal", "restricted".
    """

    artifact_id: str
    artifact_type: str
    source_project: str
    source_path: str
    source_commit: str = ""
    sensitivity: str = "internal"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "source_project": self.source_project,
            "source_path": self.source_path,
            "source_commit": self.source_commit,
            "sensitivity": self.sensitivity,
        }
