"""Heterogeneous source format normalization.

Converts raw source artifacts (CSV rows, JSON exports, Markdown notes)
into canonical GRE record schemas: HardwareRunRecord,
SierpinskiExperimentRecord, and CalibrationSnapshot.

Every normalizer:
1. Reads raw data from a source file or dict
2. Maps source-specific field names to canonical schema fields
3. Applies default values for missing required fields
4. Returns a normalized record plus any validation warnings
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Tuple
from enum import Enum
import re
import math

from .schemas import (
    HardwareRunRecord,
    SierpinskiExperimentRecord,
    CalibrationSnapshot,
    ExperimentMetadata,
    ExperimentTag,
    CircuitFamily,
    BackendName,
    ArtifactDescriptor,
)
from .provenance import ProvenanceSidecar, TransformStep


# -----------------------------------------------------------------------------
# Normalization result
# -----------------------------------------------------------------------------

@dataclass
class NormalizationWarning:
    """A warning produced during normalization."""
    field: str
    message: str
    severity: str = "warning"  # "warning" | "error"


@dataclass
class NormalizationResult:
    """Result of normalizing a source artifact."""
    record: Any  # HardwareRunRecord | SierpinskiExperimentRecord | CalibrationSnapshot
    provenance: ProvenanceSidecar
    warnings: List[NormalizationWarning] = field(default_factory=list)
    normalization_steps: List[TransformStep] = field(default_factory=list)
    artifact_id: str = ""


# -----------------------------------------------------------------------------
# Field name mappings
# -----------------------------------------------------------------------------

# Common field aliases: source_name → canonical_name
HARDWARE_RUN_ALIASES: Dict[str, str] = {
    "experiment_id": "experiment_id",
    "experimentId": "experiment_id",
    "run_id": "experiment_id",
    "runId": "experiment_id",
    "id": "experiment_id",
    "project": "project",
    "date": "date",
    "timestamp": "date",
    "run_date": "date",
    "backend": "backend",
    "backend_name": "backend",
    "hypothesis": "hypothesis_tag",
    "hypothesis_tag": "hypothesis_tag",
    "tag": "hypothesis_tag",
    "circuit_family": "circuit_family",
    "circuitType": "circuit_family",
    "type": "circuit_family",
    "shots": "shots",
    "n_shots": "shots",
    "num_shots": "shots",
    "qubit_count": "qubit_count",
    "n_qubits": "qubit_count",
    "num_qubits": "qubit_count",
    "depth": "depth",
    "circuit_depth": "depth",
    "gate_count": "depth",  # approximate
    "fidelity": "fidelity",
    "phi_deviation": "phi_deviation",
    "phi_dev": "phi_deviation",
    "sierpinski_score": "sierpinski_score",
    "score": "sierpinski_score",
    "notes": "notes",
    "description": "notes",
}


SIERPINSKI_ALIASES: Dict[str, str] = {
    "recursion_level": "recursion_level",
    "level": "recursion_level",
    "l": "recursion_level",
    "route": "route",
    "generation_route": "route",
    "hausdorff_dimension": "hausdorff_dimension",
    "dim_H": "hausdorff_dimension",
    "depth_invariant_fixed_point": "depth_invariant_fixed_point",
    "fixed_point": "depth_invariant_fixed_point",
    "1/phi": "depth_invariant_fixed_point",
    "depth_invariant_confidence": "depth_invariant_confidence",
    "confidence": "depth_invariant_confidence",
    "void_encoding_used": "void_encoding_used",
    "void_used": "void_encoding_used",
    "fractal_graph_nodes": "fractal_graph_nodes",
    "graph_nodes": "fractal_graph_nodes",
    "fractal_graph_edges": "fractal_graph_edges",
    "graph_edges": "fractal_graph_edges",
}


CALIBRATION_ALIASES: Dict[str, str] = {
    "snapshot_id": "snapshot_id",
    "calibration_id": "snapshot_id",
    "backend": "backend",
    "backend_name": "backend",
    "timestamp": "timestamp",
    "date": "timestamp",
    "t1_times": "t1_times",
    "t2_times": "t2_times",
    "readout_errors": "readout_errors",
    "gate_errors": "gate_errors",
    "qubit_freqs": "qubit_freqs",
    "readouts": "readouts",
    "connectivity": "connectivity",
}


# -----------------------------------------------------------------------------
# Default values
# -----------------------------------------------------------------------------

KNOWN_BACKENDS: Dict[str, str] = {
    "ibmq_qasm_simulator": "ibmq_qasm_simulator",
    "ibmq_perth": "ibmq_perth",
    "ibmq_guadalupe": "ibmq_guadalupe",
    "ibmq_manila": "ibmq_manila",
    "ibmq_lima": "ibmq_lima",
    "ibm_qasm_simulator": "ibmq_qasm_simulator",
    "aer_simulator": "aer_simulator",
    "local_aer": "aer_simulator",
    "ibm_perth": "ibmq_perth",
    "ibm_guadalupe": "ibmq_guadalupe",
    "ibm_manila": "ibmq_manila",
    "ibm_lima": "ibmq_lima",
}


def _normalize_backend(value: Optional[str]) -> str:
    """Normalize backend name to canonical form."""
    if not value:
        return "unknown"
    v = value.lower().strip()
    return KNOWN_BACKENDS.get(v, v)


def _normalize_date(value: Optional[str]) -> str:
    """Normalize date to ISO-8601 string."""
    if not value:
        return datetime.utcnow().isoformat() + "Z"
    v = str(value).strip()
    # Already ISO format
    if "T" in v or "Z" in v:
        return v
    # Try common formats
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(v, fmt)
            return dt.isoformat() + "Z"
        except ValueError:
            pass
    return v


def _normalize_hypothesis_tag(value: Optional[str]) -> ExperimentTag:
    """Normalize hypothesis tag to ExperimentTag enum."""
    if not value:
        return ExperimentTag.OTHER
    v = str(value).lower().strip()
    mapping = {
        "fixed_point_1_over_phi": ExperimentTag.FIXED_POINT_1_OVER_PHI,
        "1/phi": ExperimentTag.FIXED_POINT_1_OVER_PHI,
        "1/phi fixed point": ExperimentTag.FIXED_POINT_1_OVER_PHI,
        "depth_invariant": ExperimentTag.FIXED_POINT_1_OVER_PHI,
        "sierpinski_depth_invariant": ExperimentTag.SIERPINSKI_DEPTH_INVARIANT,
        "structural_encoding": ExperimentTag.STRUCTURAL_ENCODING,
        "qutrit_mapping": ExperimentTag.QUATRIT_MAPPING,
        "lc_resonator": ExperimentTag.LC_RESONATOR,
        "multiband_resonance": ExperimentTag.MULTIBAND_RESONANCE,
        "plasmonic_redshift": ExperimentTag.PLASMONIC_REDSHIFT,
        "quantum_ising_critical": ExperimentTag.QUANTUM_ISING_CRITICAL,
        "entropy_extraction": ExperimentTag.ENTROPY_EXTRACTION,
        "decoherence_free_subspace": ExperimentTag.DECOHERENCE_FREE_SUBSPACE,
        "graph_state_transfer": ExperimentTag.GRAPH_STATE_TRANSFER,
    }
    for key, tag in mapping.items():
        if key in v:
            return tag
    return ExperimentTag.OTHER


def _normalize_circuit_family(value: Optional[str]) -> CircuitFamily:
    """Normalize circuit family to CircuitFamily enum."""
    if not value:
        return CircuitFamily.UNKNOWN
    v = str(value).lower().strip()
    mapping = {
        "fractal_walk": CircuitFamily.FRACTAL_WALK,
        "walk": CircuitFamily.FRACTAL_WALK,
        "staggered_walk": CircuitFamily.STAGGERED_WALK,
        "coined_walk": CircuitFamily.COINED_WALK,
        "qaoa_style": CircuitFamily.QAOA_STYLE,
        "variational": CircuitFamily.VARIATIONAL,
        "gate_based": CircuitFamily.GATE_BASED,
        "measurement_based": CircuitFamily.MEASUREMENT_BASED,
    }
    for key, fam in mapping.items():
        if key in v:
            return fam
    return CircuitFamily.UNKNOWN


def _parse_metrics_dict(value: Any) -> Dict[str, float]:
    """Parse a metrics field into a canonical float dict."""
    if not value:
        return {}
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            try:
                result[str(k)] = float(v)
            except (ValueError, TypeError):
                pass
        return result
    if isinstance(value, str):
        result = {}
        for match in re.finditer(r"([\w_]+)\s*[=:]\s*([\d.]+)", value):
            k, v = match.groups()
            try:
                result[k.strip()] = float(v)
            except ValueError:
                pass
        return result
    return {}


def _parse_gate_counts(value: Any) -> Dict[str, int]:
    """Parse a gate_counts field into an int dict."""
    if not value:
        return {}
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            try:
                result[str(k)] = int(v)
            except (ValueError, TypeError):
                pass
        return result
    return {}


# -----------------------------------------------------------------------------
# Hardware run normalizer
# -----------------------------------------------------------------------------

def normalize_hardware_run(
    data: Dict[str, Any],
    provenance: Optional[ProvenanceSidecar] = None,
    source_project: str = "",
) -> NormalizationResult:
    """Normalize a raw dict or record into HardwareRunRecord.

    Applies field aliases, type coercion, and defaults.

    Args:
        data: Raw source data dict.
        provenance: Existing ProvenanceSidecar (will be enhanced).
        source_project: Source project name.

    Returns:
        NormalizationResult containing HardwareRunRecord and provenance.
    """
    warnings: List[NormalizationWarning] = []
    steps: List[TransformStep] = []
    provenance = provenance or ProvenanceSidecar(source_project=source_project)

    # Apply field aliases
    normalized: Dict[str, Any] = {}
    for raw_key, value in data.items():
        canonical = HARDWARE_RUN_ALIASES.get(raw_key, raw_key)
        normalized[canonical] = value

    # Required fields with fallbacks
    experiment_id = str(normalized.get("experiment_id", f"import-{id(data)}"))
    project = normalized.get("project", source_project or "unknown")
    date = _normalize_date(normalized.get("date"))
    hypothesis_tag = _normalize_hypothesis_tag(normalized.get("hypothesis_tag"))
    circuit_family = _normalize_circuit_family(normalized.get("circuit_family"))

    meta = ExperimentMetadata(
        experiment_id=experiment_id,
        project=project,
        date=date,
        hypothesis_tag=hypothesis_tag,
        circuit_family=circuit_family,
        notes=str(normalized.get("notes", "")),
    )

    # Metrics
    metrics_raw = normalized.get("metrics", {})
    if isinstance(metrics_raw, dict):
        observed_metrics = _parse_metrics_dict(metrics_raw)
    else:
        observed_metrics = {}

    # Flat metrics fields also count
    for key in ["fidelity", "phi_deviation", "sierpinski_score", "lambda2",
                "state_transfer_fidelity", "state_transfer_step"]:
        if key in normalized and key not in observed_metrics:
            try:
                observed_metrics[key] = float(normalized[key])
            except (ValueError, TypeError):
                pass

    fidelity = observed_metrics.get("fidelity")
    phi_deviation = observed_metrics.get("phi_deviation")
    sierpinski_score = observed_metrics.get("sierpinski_score")

    # Required numeric fields
    backend = _normalize_backend(normalized.get("backend"))
    try:
        qubit_count = int(normalized.get("qubit_count", 0))
    except (ValueError, TypeError):
        qubit_count = 0
        warnings.append(NormalizationWarning("qubit_count", f"Could not parse: {normalized.get('qubit_count')}"))

    try:
        depth = int(normalized.get("depth", 0))
    except (ValueError, TypeError):
        depth = 0
        warnings.append(NormalizationWarning("depth", f"Could not parse: {normalized.get('depth')}"))

    try:
        shots = int(normalized.get("shots", 0))
    except (ValueError, TypeError):
        shots = 0
        warnings.append(NormalizationWarning("shots", f"Could not parse: {normalized.get('shots')}"))

    gate_counts = _parse_gate_counts(normalized.get("gate_counts", {}))

    is_synthetic = bool(data.get("is_synthetic", False))
    confidence_tier = str(data.get("confidence_tier", "inferred"))
    # Infer confidence tier from data quality if not explicitly set
    if not data.get("confidence_tier") and fidelity is not None:
        if fidelity >= 0.9:
            confidence_tier = "measured"
        elif fidelity >= 0.7:
            confidence_tier = "inferred"
        elif fidelity is not None:
            confidence_tier = "extrapolated"

    record = HardwareRunRecord(
        metadata=meta,
        backend=backend,
        qubit_count=qubit_count,
        depth=depth,
        shots=shots,
        gate_counts=gate_counts,
        expected_metrics=list(observed_metrics.keys()),
        observed_metrics=observed_metrics,
        fidelity=fidelity,
        phi_deviation=phi_deviation,
        sierpinski_score=sierpinski_score,
        is_synthetic=is_synthetic,
        confidence_tier=confidence_tier,
        provenance=provenance,
        backend_generation=normalized.get("backend_generation", "unknown"),
        calibration_snapshot_id=normalized.get("calibration_snapshot_id"),
    )

    steps.append(TransformStep(
        step_id=0,
        transform_type="normalize",
        description="Raw dict → HardwareRunRecord",
        parameters={"source_keys": list(data.keys())},
        tool="gre.research.normalizers.normalize_hardware_run",
    ))
    provenance.add_transform("normalize", "Dict → HardwareRunRecord", {"fields_normalized": len(normalized)})

    return NormalizationResult(
        record=record,
        provenance=provenance,
        warnings=warnings,
        normalization_steps=steps,
        artifact_id=experiment_id,
    )


# -----------------------------------------------------------------------------
# Sierpinski experiment normalizer
# -----------------------------------------------------------------------------

def normalize_sierpinski_experiment(
    data: Dict[str, Any],
    provenance: Optional[ProvenanceSidecar] = None,
    source_project: str = "",
) -> NormalizationResult:
    """Normalize a raw dict into SierpinskiExperimentRecord.

    Args:
        data: Raw source data dict.
        provenance: Existing ProvenanceSidecar.
        source_project: Source project name.

    Returns:
        NormalizationResult containing SierpinskiExperimentRecord.
    """
    warnings: List[NormalizationWarning] = []
    provenance = provenance or ProvenanceSidecar(source_project=source_project)

    # First normalize as hardware run
    hw_result = normalize_hardware_run(data, provenance, source_project)
    hw_record = hw_result.record
    warnings.extend(hw_result.warnings)

    # Extract Sierpinski-specific fields
    sierpinski_data: Dict[str, Any] = {}
    for raw_key, value in data.items():
        canonical = SIERPINSKI_ALIASES.get(raw_key, raw_key)
        sierpinski_data[canonical] = value

    # Parse Sierpinski-specific fields
    try:
        recursion_level = int(sierpinski_data.get("recursion_level", 0))
    except (ValueError, TypeError):
        recursion_level = hw_record.depth
        warnings.append(NormalizationWarning("recursion_level", "Defaulted to depth"))

    hausdorff_dimension = sierpinski_data.get("hausdorff_dimension", 1.5849625)

    try:
        structural_depth = int(sierpinski_data.get("structural_encoding_depth", 0))
    except (ValueError, TypeError):
        structural_depth = 0

    depth_invariant_fixed_point = None
    fp_raw = sierpinski_data.get("depth_invariant_fixed_point")
    if fp_raw is not None:
        try:
            depth_invariant_fixed_point = float(fp_raw)
        except (ValueError, TypeError):
            pass

    depth_invariant_confidence = None
    conf_raw = sierpinski_data.get("depth_invariant_confidence")
    if conf_raw is not None:
        try:
            depth_invariant_confidence = float(conf_raw)
        except (ValueError, TypeError):
            pass

    route = str(sierpinski_data.get("route", "ifs"))
    void_encoding_used = bool(sierpinski_data.get("void_encoding_used", False))

    try:
        fractal_graph_nodes = int(sierpinski_data.get("fractal_graph_nodes", 0))
    except (ValueError, TypeError):
        fractal_graph_nodes = hw_record.qubit_count

    try:
        fractal_graph_edges = int(sierpinski_data.get("fractal_graph_edges", 0))
    except (ValueError, TypeError):
        fractal_graph_edges = hw_record.depth

    sier_record = SierpinskiExperimentRecord(
        hardware_record=hw_record,
        recursion_level=recursion_level,
        hausdorff_dimension=hausdorff_dimension,
        structural_encoding_depth=structural_depth,
        depth_invariant_fixed_point=depth_invariant_fixed_point,
        depth_invariant_confidence=depth_invariant_confidence,
        route=route,
        void_encoding_used=void_encoding_used,
        fractal_graph_nodes=fractal_graph_nodes,
        fractal_graph_edges=fractal_graph_edges,
    )

    hw_record.provenance.add_transform(
        "normalize_sierpinski",
        "Dict → SierpinskiExperimentRecord",
        {"recursion_level": recursion_level, "route": route}
    )

    return NormalizationResult(
        record=sier_record,
        provenance=hw_record.provenance,
        warnings=warnings,
        normalization_steps=hw_result.normalization_steps,
        artifact_id=hw_record.metadata.experiment_id,
    )


# -----------------------------------------------------------------------------
# Calibration snapshot normalizer
# -----------------------------------------------------------------------------

def normalize_calibration_snapshot(
    data: Dict[str, Any],
    provenance: Optional[ProvenanceSidecar] = None,
    source_project: str = "",
) -> NormalizationResult:
    """Normalize a raw dict into CalibrationSnapshot.

    Args:
        data: Raw source data dict.
        provenance: Existing ProvenanceSidecar.
        source_project: Source project name.

    Returns:
        NormalizationResult containing CalibrationSnapshot.
    """
    warnings: List[NormalizationWarning] = []
    provenance = provenance or ProvenanceSidecar(source_project=source_project)

    normalized: Dict[str, Any] = {}
    for raw_key, value in data.items():
        canonical = CALIBRATION_ALIASES.get(raw_key, raw_key)
        normalized[canonical] = value

    snapshot_id = str(normalized.get("snapshot_id", f"cal-{id(data)}"))
    backend = _normalize_backend(normalized.get("backend", ""))
    timestamp = _normalize_date(normalized.get("timestamp"))

    # Parse nested dict fields
    t1_times = _parse_nested_floats(normalized.get("t1_times", {}))
    t2_times = _parse_nested_floats(normalized.get("t2_times", {}))
    readout_errors = _parse_nested_floats(normalized.get("readout_errors", {}))
    gate_errors = _parse_nested_floats(normalized.get("gate_errors", {}))
    qubit_freqs = _parse_nested_floats(normalized.get("qubit_freqs", {}))
    readouts = _parse_nested_floats(normalized.get("readouts", {}))

    connectivity_raw = normalized.get("connectivity", [])
    connectivity: List[tuple] = []
    for edge in connectivity_raw:
        if isinstance(edge, (list, tuple)) and len(edge) == 2:
            connectivity.append((int(edge[0]), int(edge[1])))
        elif isinstance(edge, str):
            parts = edge.replace("(", "").replace(")", "").split(",")
            if len(parts) == 2:
                try:
                    connectivity.append((int(parts[0].strip()), int(parts[1].strip())))
                except ValueError:
                    pass

    raw_calibration_ref = str(normalized.get("raw_calibration_ref", ""))
    is_synthetic = bool(data.get("is_synthetic", False))
    confidence_tier = str(data.get("confidence_tier", "measured"))

    record = CalibrationSnapshot(
        snapshot_id=snapshot_id,
        backend=backend,
        timestamp=timestamp,
        t1_times=t1_times,
        t2_times=t2_times,
        readout_errors=readout_errors,
        gate_errors=gate_errors,
        qubit_freqs=qubit_freqs,
        readouts=readouts,
        connectivity=connectivity,
        raw_calibration_ref=raw_calibration_ref,
        is_synthetic=is_synthetic,
        confidence_tier=confidence_tier,
        provenance=provenance,
    )

    provenance.add_transform(
        "normalize",
        "Dict → CalibrationSnapshot",
        {"backend": backend}
    )

    return NormalizationResult(
        record=record,
        provenance=provenance,
        warnings=warnings,
        normalization_steps=[],
        artifact_id=snapshot_id,
    )


def _parse_nested_floats(data: Any) -> Dict[str, float]:
    """Parse a nested dict of values into Dict[str, float]."""
    if not data:
        return {}
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            try:
                result[str(k)] = float(v)
            except (ValueError, TypeError):
                pass
        return result
    return {}


# -----------------------------------------------------------------------------
# Markdown frontmatter parser
# -----------------------------------------------------------------------------

def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter from Markdown content.

    Args:
        content: Markdown text with optional YAML frontmatter.

    Returns:
        Tuple of (frontmatter dict, body text).
    """
    if content.startswith("---"):
        parts = content[3:].split("---", 1)
        if len(parts) == 2:
            fm_text, body = parts
            try:
                import yaml
                fm = yaml.safe_load(fm_text) or {}
                return fm, body.strip()
            except ImportError:
                # Fallback: simple key: value parsing
                fm = {}
                for line in fm_text.strip().split("\n"):
                    if ": " in line or ":" in line:
                        key_val = line.split(":", 1)
                        if len(key_val) == 2:
                            fm[key_val[0].strip()] = key_val[1].strip()
                return fm, body.strip()
    return {}, content


def normalize_markdown_experiment(
    md_content: str,
    provenance: Optional[ProvenanceSidecar] = None,
    source_project: str = "",
) -> NormalizationResult:
    """Normalize a Markdown file into a SierpinskiExperimentRecord.

    Parses YAML frontmatter for structured data and Markdown body for notes.

    Args:
        md_content: Content of Markdown file.
        provenance: Existing ProvenanceSidecar.
        source_project: Source project name.

    Returns:
        NormalizationResult containing SierpinskiExperimentRecord.
    """
    frontmatter, body = parse_frontmatter(md_content)
    if body:
        frontmatter.setdefault("notes", body)

    return normalize_sierpinski_experiment(frontmatter, provenance, source_project)


# -----------------------------------------------------------------------------
# Auto-detect and normalize
# -----------------------------------------------------------------------------

def auto_normalize(
    data: Dict[str, Any],
    provenance: Optional[ProvenanceSidecar] = None,
    source_project: str = "",
    record_kind: str = "",
) -> NormalizationResult:
    """Auto-detect record type and normalize accordingly.

    Args:
        data: Raw source data dict.
        provenance: Existing ProvenanceSidecar.
        source_project: Source project name.
        record_kind: Hint for record type ("hardware_run", "sierpinski_experiment",
            "calibration"). If empty, auto-detects from fields.

    Returns:
        NormalizationResult with appropriate record type.
    """
    if record_kind == "hardware_run":
        return normalize_hardware_run(data, provenance, source_project)
    elif record_kind == "sierpinski_experiment":
        return normalize_sierpinski_experiment(data, provenance, source_project)
    elif record_kind == "calibration":
        return normalize_calibration_snapshot(data, provenance, source_project)

    # Auto-detect from fields
    if "snapshot_id" in data or "calibration_id" in data:
        return normalize_calibration_snapshot(data, provenance, source_project)
    elif "recursion_level" in data or "route" in data or "fractal_graph_nodes" in data:
        return normalize_sierpinski_experiment(data, provenance, source_project)
    elif "backend" in data or "fidelity" in data or "depth" in data:
        return normalize_hardware_run(data, provenance, source_project)
    else:
        # Default to hardware run
        return normalize_hardware_run(data, provenance, source_project)
