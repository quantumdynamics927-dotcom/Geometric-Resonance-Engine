#!/usr/bin/env python3
"""Import newly discovered IBM Quantum jobs into the GRE corpus.

Discovered job sources:
  - D:/Somnath-PROJECT/qasmsierpinski_tmt_phase4s_ibm_kin/  (6 jobs, ibm_kingston + ibm_fez)
  - D:/Somnath-PROJECT/Jobs-to-check/                        (4 jobs, ibm_kingston + ibm_marrakesh)
  - D:/Somnath-PROJECT/Jobs/                                 (ibm_marrakesh teleport job)

For each job:
  1. Read the -info.json to get backend, date, shots, program type
  2. Read the -result.json to extract measurement outcomes
  3. Decode QPY circuit to determine circuit_family and qubit count
  4. Classify as hardware_run or sierpinski_experiment based on circuit type
  5. Write to imports/<project>/<artifact_id>.json with full provenance

Run:
    python scripts/import_new_ibm_jobs.py [--dry-run] [--project PROJECT]
"""

import argparse
import base64
import enum
import json
import struct
import sys
import zlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Add gre to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from gre.research.schemas import (
    HardwareRunRecord,
    SierpinskiExperimentRecord,
    ExperimentMetadata,
    ExperimentTag,
    CircuitFamily,
    BackendName,
    EvidenceClass,
    ValidationTier,
    BackendGeneration,
    CalibrationCompleteness,
)
from gre.research.provenance import ProvenanceSidecar, TransformStep


# ---------------------------------------------------------------------------
# Job classification
# ---------------------------------------------------------------------------

@dataclass
class JobInfo:
    """Parsed IBM Quantum job info."""
    job_id: str
    backend: str
    created: str  # ISO-8601
    program_id: str  # 'sampler', 'executor', etc.
    shots: int
    qubit_count: int  # from circuit
    circuit_family: str
    experiment_id: str
    project: str
    hypothesis_tag: str
    route: str
    depth: int
    calibration_snapshot_id: str
    evidence_class: str = "historical_real"
    validation_tier: str = "benchmarked"
    backend_generation: str = "unknown"
    # Metrics (if extractable from result)
    fidelity: float | None = None
    phi_deviation: float | None = None
    sierpinski_score: float | None = None
    depth_invariant_fixed_point: float | None = None
    depth_invariant_confidence: float | None = None
    lambda2: float | None = None
    # Result data
    measurement_counts: dict | None = None
    # Source
    source_path: str = ""
    raw_data_ref: str = ""


# ---------------------------------------------------------------------------
# QPY v17 decoder (minimal — just enough to get qubit count + gate ops)
# ---------------------------------------------------------------------------

def decode_qpy_size_prefixed(b64: str) -> bytes:
    """Decode a base64 QPY v17 size-prefixed circuit."""
    data = base64.b64decode(b64)

    # QPY format: each item is: uint32 little-endian size prefix + payload
    items = []
    i = 0
    while i < len(data):
        if i + 4 > len(data):
            break
        size = struct.unpack('<I', data[i:i+4])[0]
        i += 4
        if i + size > len(data):
            break
        items.append(data[i:i+size])
        i += size
    return b''.join(items) if items else data


def inspect_qpy_circuit(b64_data: str) -> dict:
    """Extract key info from a QPY v17 base64 circuit without full QPY dep.

    Returns dict with: qubit_count, depth (approximate), gate_ops (count), is_sierpinski
    """
    try:
        raw = decode_qpy_size_prefixed(b64_data)
    except Exception:
        return {"qubit_count": 0, "depth": 0, "gate_ops": 0, "is_sierpinski": False}

    # Count "SI" magic bytes (Sierpinski gate marker in these circuits)
    # Also look for known gate names in the raw bytes
    si_markers = raw.count(b'SI')
    cz_count = raw.count(b'cz ')
    cx_count = raw.count(b'cx ')
    x_count  = raw.count(b'x  ')
    rz_count = raw.count(b'rz ')
    sx_count = raw.count(b'sx')

    # Approximate gate count
    gate_ops = cz_count + cx_count + x_count + rz_count + sx_count

    # Qubit count: look for the largest q in the circuit
    # Format: 'q<N>' as ASCII in the header
    qubit_indices = set()
    for match in __import__('re').finditer(rb'q(\d+)', raw[:2000]):
        qubit_indices.add(int(match.group(1)))
    qubit_count = max(qubit_indices) + 1 if qubit_indices else 0

    # If we couldn't find from header, estimate from gate ops and connectivity
    if qubit_count == 0:
        # Use the max edge index in CZ/CX ops as a proxy
        edge_max = 0
        for match in __import__('re').finditer(rb'c[zx] (\d+),(\d+)', raw):
            a, b = int(match.group(1)), int(match.group(2))
            edge_max = max(edge_max, a, b)
        qubit_count = max(edge_max + 1, 5)

    # Depth: gate schedule sections
    depth = raw.count(b'schedule') + gate_ops // max(qubit_count, 1)

    is_sierpinski = si_markers > 0 or b'SIERPINSKI' in raw[:500]

    return {
        "qubit_count": qubit_count,
        "depth": min(depth, 100),  # cap for sanity
        "gate_ops": gate_ops,
        "is_sierpinski": is_sierpinski,
        "cz_count": cz_count,
        "cx_count": cx_count,
    }


# ---------------------------------------------------------------------------
# OPENQASM 3.0 circuit inspector
# ---------------------------------------------------------------------------

def inspect_openqasm_circuit(qasm_str: str) -> dict:
    """Extract info from an inline OPENQASM 3.0 circuit string.

    Returns dict with: qubit_count, gate_ops, is_sierpinski, is_phi_encoded
    """
    lines = [l.strip() for l in qasm_str.split('\n')
             if l.strip() and not l.strip().startswith('//')]

    qubit_count = 0
    gate_ops = 0
    is_sierpinski = False
    is_phi_encoded = False
    has_cz = False
    has_rx = False
    has_conditional = False

    for line in lines:
        # Count qubits
        for match in __import__('re').finditer(r'q(\d+)', line):
            qubit_count = max(qubit_count, int(match.group(1)) + 1)
        # Gate ops
        for gate in ['cx', 'cz', 'rx', 'ry', 'rz', 'sx', 'x', 'h', 't', 's']:
            if f' {gate} ' in line or f'({gate})' in line or line.startswith(gate):
                gate_ops += 1
                if gate == 'cz':
                    has_cz = True
                if gate == 'rx':
                    has_rx = True
        # Phi encoding
        if 'phi' in line.lower() or '1.618' in line or '0.618' in line:
            is_phi_encoded = True
        # Sierpinski
        if 'sierpinski' in line.lower():
            is_sierpinski = True
        # Conditional classical control
        if 'if(' in line:
            has_conditional = True

    is_sierpinski = is_sierpinski or (is_phi_encoded and has_cz and qubit_count > 5)

    return {
        "qubit_count": qubit_count,
        "gate_ops": gate_ops,
        "is_sierpinski": is_sierpinski,
        "is_phi_encoded": is_phi_encoded,
        "has_cz": has_cz,
        "has_rx": has_rx,
        "has_conditional": has_conditional,
    }


# ---------------------------------------------------------------------------
# Backend generation inference
# ---------------------------------------------------------------------------

BACKEND_GENERATION_MAP = {
    "ibm_kingston": "ibm_herron",
    "ibm_fez": "ibm_herron",
    "ibm_marrakesh": "unknown",  # determine from job date
    "ibmq_perth": "ibm_falcon",
    "ibmq_lima": "ibm_falcon",
    "ibmq_manila": "ibm_falcon",
    "ibmq_guadalupe": "ibm_eagle",
    "ibmq_qasm_simulator": "simulator",
    "aer_simulator": "simulator",
}

def infer_backend_generation(backend: str) -> str:
    return BACKEND_GENERATION_MAP.get(backend, "unknown")

def infer_calibration_snapshot_id(backend: str, date_str: str) -> str:
    """Return the nearest calibration snapshot ID for a backend/date."""
    # Map backend + approximate date to calibration snapshot
    date = date_str[:10]  # YYYY-MM-DD
    if backend == "ibm_kingston":
        return "cal-ibm-kingston-20260423"
    elif backend == "ibm_fez":
        return "cal-ibm-fez-20260305"
    elif backend == "ibm_marrakesh":
        # Marrakesh doesn't have a calibration snapshot yet
        return ""
    return ""

# ---------------------------------------------------------------------------
# Job parsing
# ---------------------------------------------------------------------------

def parse_job_info(info_path: Path, result_path: Path | None) -> JobInfo | None:
    """Parse a single IBM job pair into a JobInfo record."""
    with open(info_path, encoding="utf-8") as f:
        info = json.load(f)

    job_id = info.get("id", "")
    backend = info.get("backend", "unknown")
    created = info.get("created", "")
    program_id = info.get("program", {}).get("id", "")
    params = info.get("params", {})
    qprog = params.get("quantum_program", {})
    shots = qprog.get("shots", 0)

    qubit_count = 0
    circuit_family = "unknown"
    hypothesis_tag = "unknown"
    route = ""
    depth = 0
    is_sierpinski = False
    is_phi_encoded = False
    has_conditional = False

    # Try to extract circuit info
    items = qprog.get("items", [])
    for item in items:
        circuit = item.get("circuit", {})
        # QPY format
        if "circuit_b64" in circuit:
            b64 = circuit["circuit_b64"]
            qpy_info = inspect_qpy_circuit(b64)
            qubit_count = qpy_info["qubit_count"]
            depth = qpy_info["depth"]
            is_sierpinski = qpy_info["is_sierpinski"]
            circuit_family = "fractal_walk" if is_sierpinski else "generic"
        # OPENQASM 3.0 format
        elif "openqasm" in circuit:
            qasm_str = circuit.get("openqasm", "")
            qasm_info = inspect_openqasm_circuit(qasm_str)
            qubit_count = qasm_info["qubit_count"]
            is_sierpinski = qasm_info["is_sierpinski"]
            is_phi_encoded = qasm_info["is_phi_encoded"]
            has_conditional = qasm_info["has_conditional"]
            circuit_family = "fractal_walk" if is_sierpinski else "teleport"
        # Check circuit name for hints
        circuit_label = circuit.get("label", "") or circuit.get("name", "")
        if circuit_label:
            cl = circuit_label.lower()
            if "sierpinski" in cl or "ifs" in cl:
                is_sierpinski = True
                circuit_family = "fractal_walk"
            elif "phi" in cl or "merkaba" in cl:
                is_phi_encoded = True

    # Determine experiment type
    if is_sierpinski:
        project = "sierpinski"
        # Extract route from program context or default
        route = _infer_route(info_path, is_sierpinski=True)
        # Hypothesis tag based on route
        hypothesis_tag = "sierpinski_depth_invariant"
        # Depth inference
        depth = _infer_depth(info_path, qprog)
    elif is_phi_encoded or has_conditional:
        project = "tmt"
        circuit_family = "phi_encoding"
        hypothesis_tag = "phi_encoding"
        route = "phi"
    else:
        project = "qsg"
        circuit_family = "generic"
        hypothesis_tag = "teleport"
        route = ""

    # Build experiment_id
    date_short = created[:10].replace("-", "")  # YYYYMMDD
    if is_sierpinski:
        # Use the job id for uniqueness
        experiment_id = f"sierpinski-{backend}-{job_id[:8]}"
    elif is_phi_encoded:
        experiment_id = f"ibm-{backend}-phi-{date_short}"
    else:
        experiment_id = f"ibm-{backend}-{job_id[:8]}"

    # Parse result data if available
    fidelity = None
    measurement_counts = None
    result_n_qubits = 0
    if result_path:
        rp = result_path if isinstance(result_path, Path) else Path(result_path)
        if rp.exists():
            try:
                with open(rp, encoding="utf-8") as f:
                    result = json.load(f)
                # Dispatch by result format
                rdata = _extract_result_data(result)
                if rdata is not None:
                    result_n_qubits, counts_str = rdata
                    if result_n_qubits > 0 and counts_str:
                        measurement_counts = _decode_bitstring_counts(
                            counts_str, shots, result_n_qubits
                        )
                        if measurement_counts and shots > 0:
                            fidelity = _compute_fidelity_from_counts(measurement_counts, shots)
                    if result_n_qubits > 0:
                        qubit_count = result_n_qubits
            except Exception as e:
                print(f"  Warning: could not parse result for {job_id}: {e}")

    # Override qubit_count if we got it from the result
    if result_n_qubits > 0:
        qubit_count = result_n_qubits

    return JobInfo(
        job_id=job_id,
        backend=backend,
        created=created,
        program_id=program_id,
        shots=shots,
        qubit_count=qubit_count,
        circuit_family=circuit_family,  # string — will be converted in create_*_record()
        experiment_id=experiment_id,
        project=project,
        hypothesis_tag=hypothesis_tag,  # string — will be converted in create_*_record()
        route=route,
        depth=depth,
        calibration_snapshot_id=infer_calibration_snapshot_id(backend, created),
        evidence_class="historical_real",
        validation_tier="benchmarked",
        backend_generation=infer_backend_generation(backend),
        fidelity=fidelity,
        measurement_counts=measurement_counts,
        source_path=str(info_path),
        raw_data_ref=str(result_path) if result_path else "",
    )


def _infer_route(info_path: Path, is_sierpinski: bool) -> str:
    """Infer the Sierpinski route from the file path and content."""
    path_str = str(info_path).lower()
    if "pascal" in path_str:
        return "pascal"
    elif "hanoi" in path_str:
        return "hanoi"
    elif "rule90" in path_str or "rule_90" in path_str:
        return "rule90"
    elif "ifs" in path_str:
        return "ifs"
    elif "chaos" in path_str:
        return "chaos_game"
    elif "lucas" in path_str:
        return "lucas"
    elif "julia" in path_str:
        return "julia"
    return "ifs"  # default


def _infer_depth(info_path: Path, qprog: dict) -> int:
    """Infer circuit depth from QPY circuit structure."""
    items = qprog.get("items", [])
    if not items:
        return 0
    # Count gate layers from schedule or look for depth in circuit label
    for item in items:
        circuit = item.get("circuit", {})
        label = circuit.get("label", "") or circuit.get("name", "")
        # Try to extract depth from label like "circuit-164-32"
        import re
        m = re.search(r'-(\d+)$', label)
        if m:
            return int(m.group(1))
    return 5  # default


def _extract_result_data(result: dict) -> tuple[int, str] | None:
    """Extract (n_qubits, counts_string) from any IBM result format.

    Handles three formats:
    1. ``{"data": [{results: {c: {shape: [shots, n_qubits], data: b64}}}}``  (qasmsierpinski dir)
    2. ``{"results": [{data: {c: {samples: [hex, ...], num_bits}}}]}}``         (d6kvddg etc)
    3. ``{"__type__": "PrimitiveResult", "value": {pub_results: [...]}}``    (Sampler v2)

    Returns (n_qubits, base64_counts_string) or None if parsing fails.
    """
    # Format 1: {"data": [{results: {c: {shape: [shots, n_qubits], data: b64}}}}]}
    if result.get("data"):
        try:
            entry = result["data"][0]
            meas = entry.get("results", {}).get("c", {})
            if isinstance(meas, dict):
                shape = meas.get("shape", [])
                counts_str = meas.get("data", "")
                if len(shape) >= 2 and counts_str:
                    n_qubits = shape[1]
                    return n_qubits, counts_str
        except (KeyError, IndexError, TypeError):
            pass

    # Format 2: {"results": [{data: {c: {samples: [hex, ...], num_bits}}}}]}
    if result.get("results"):
        try:
            entry = result["results"][0]
            c_data = entry.get("data", {}).get("c", {})
            if isinstance(c_data, dict):
                samples = c_data.get("samples", [])
                num_bits = c_data.get("num_bits", 0)
                if samples and num_bits > 0:
                    # Pack hex strings back into a compact bitstring representation
                    # We re-encode as a simple packed bit array (LSB-first per qubit)
                    packed = _pack_hex_samples(samples, num_bits)
                    return num_bits, packed
        except (KeyError, IndexError, TypeError):
            pass

    # Format 3: {"__type__": "PrimitiveResult", ...} with SamplerPubResult
    if result.get("__type__") == "PrimitiveResult":
        try:
            pub_results = result["value"]["pub_results"]
            if not pub_results:
                return None
            pub0 = pub_results[0]
            if pub0.get("__type__") == "SamplerPubResult":
                val = pub0["__value__"]
                databin = val["data"]["__value__"]
                fields = databin.get("fields", {})
                # Try 'c' then 'meas' for the bit array
                for fname in ["c", "meas"]:
                    if fname not in fields:
                        continue
                    bitarr = fields[fname]["__value__"]
                    arr_b64 = bitarr["array"]["__value__"]
                    num_bits = bitarr["num_bits"]
                    raw = base64.b64decode(arr_b64)
                    dec = zlib.decompress(raw)
                    packed = _pack_numpy_bit_array(dec, num_bits)
                    if packed:
                        return num_bits, packed
        except (KeyError, IndexError, TypeError, zlib.error, Exception):
            pass

    return None


def _pack_hex_samples(samples: list[str], num_bits: int) -> str:
    """Convert list of hex bitstring samples to a packed base64 bit array.

    Packs num_bits bits per shot, LSB-first, into a base64-encoded byte array.
    Returns the base64 string (without the bitstring format wrapper).
    """
    import io
    import numpy as np

    n_shots = len(samples)
    n_bytes = (n_shots * num_bits + 7) // 8
    packed = bytearray(n_bytes)

    for shot_idx, hex_str in enumerate(samples):
        # Remove '0x' prefix and parse
        val = int(hex_str, 16)
        for bit in range(num_bits):
            byte_idx = (shot_idx * num_bits + bit) // 8
            bit_idx = (shot_idx * num_bits + bit) % 8
            if (val >> bit) & 1:
                packed[byte_idx] |= 1 << bit_idx

    return base64.b64encode(bytes(packed)).decode("ascii")


def _pack_numpy_bit_array(decompressed: bytes, num_bits: int) -> str | None:
    """Unpack a numpy BitArray byte array into a packed base64 bit array.

    ``np.load(io.BytesIO(decompressed))`` gives a shape (n_shots, n_words) uint8 array
    where each row contains 8 bits per word. We extract the first num_bits bits
    per row (shot) and pack them LSB-first into a byte array.
    Returns base64-encoded packed bits or None on failure.
    """
    import io
    import numpy as np

    try:
        arr = np.load(io.BytesIO(decompressed))
    except Exception:
        return None

    if arr.ndim != 2:
        return None

    n_shots = arr.shape[0]
    n_bytes = (n_shots * num_bits + 7) // 8
    packed = bytearray(n_bytes)

    for shot_idx in range(n_shots):
        row = arr[shot_idx]
        for word_idx, byte_val in enumerate(row):
            for bit in range(8):
                global_bit = word_idx * 8 + bit
                if global_bit >= num_bits:
                    break
                byte_idx = (shot_idx * num_bits + global_bit) // 8
                bit_idx = (shot_idx * num_bits + global_bit) % 8
                if (byte_val >> bit) & 1:
                    packed[byte_idx] |= 1 << bit_idx

    return base64.b64encode(bytes(packed)).decode("ascii")


def _decode_bitstring_counts(data_b64: str, shots: int, n_qubits: int) -> dict:
    """Decode base64-encoded packed measurement bitstrings.

    The packed format stores n_qubits bits per shot, LSB-first, packed into bytes.
    ``packed_bits[shot * n_qubits + q]`` is the q-th qubit's measurement outcome
    for the shot_idx-th shot.
    """
    try:
        raw = base64.b64decode(data_b64)
        counts = {}
        for shot_idx in range(shots):
            value = 0
            for q in range(n_qubits):
                byte_idx = (shot_idx * n_qubits + q) // 8
                bit_idx = (shot_idx * n_qubits + q) % 8
                if byte_idx >= len(raw):
                    break
                bit = (raw[byte_idx] >> bit_idx) & 1
                value |= bit << q  # LSB-first: qubit 0 = bit 0
            else:
                # Only record if we successfully read all qubits
                counts[value] = counts.get(value, 0) + 1
        return counts
    except Exception:
        return {}


def _compute_fidelity_from_counts(counts: dict, shots: int) -> float | None:
    """Compute a basic fidelity estimate from measurement counts.

    For Sierpinski experiments: fidelity ≈ P(max_count) / shots.
    This is an upper bound; real fidelity requires state tomography.
    """
    if not counts or shots == 0:
        return None
    max_count = max(counts.values())
    return max_count / shots


# ---------------------------------------------------------------------------
# Import to corpus
# ---------------------------------------------------------------------------

def create_hardware_run_record(info: JobInfo) -> HardwareRunRecord:
    """Create a HardwareRunRecord from a JobInfo."""
    metadata = ExperimentMetadata(
        experiment_id=info.experiment_id,
        project=info.project,
        date=info.created[:10],
        hypothesis_tag=_hypothesis_tag_to_enum(info.hypothesis_tag),
        circuit_family=_circuit_family_to_enum(info.circuit_family),
    )
    provenance = ProvenanceSidecar(
        source_project="somnath-import",
        source_artifact_id=info.job_id,
        source_path=info.source_path,
        source_commit="",
        transform_chain=[
            TransformStep(
                step_id=0,
                transform_type="import",
                description="Imported from IBM Quantum job result file",
                parameters={"source_file": str(info.source_path)},
                tool="import_new_ibm_jobs.py",
            )
        ],
        sensitivity="internal",
        claims_supported=[],
    )
    observed = {}
    if info.fidelity is not None:
        observed["fidelity"] = info.fidelity
    if info.measurement_counts:
        observed["measurement_counts"] = info.measurement_counts
        observed["shots"] = info.shots
        observed["qubits"] = info.qubit_count
    if info.depth_invariant_fixed_point is not None:
        observed["depth_invariant_fixed_point"] = info.depth_invariant_fixed_point

    _backend = BackendName(info.backend).value if info.backend in [b.value for b in BackendName] else info.backend

    return HardwareRunRecord(
        metadata=metadata,
        backend=_backend,
        qubit_count=info.qubit_count,
        depth=info.depth,
        shots=info.shots,
        fidelity=info.fidelity,
        phi_deviation=info.phi_deviation,
        observed_metrics=observed,
        provenance=provenance,
        evidence_class=info.evidence_class,
        validation_tier=info.validation_tier,
        backend_generation=info.backend_generation,
        calibration_snapshot_id=info.calibration_snapshot_id or None,
    )


def create_sierpinski_record(info: JobInfo) -> SierpinskiExperimentRecord:
    """Create a SierpinskiExperimentRecord from a JobInfo."""
    # Build the nested hardware record
    hw_record = create_hardware_run_record(info)

    return SierpinskiExperimentRecord(
        hardware_record=hw_record,
        recursion_level=_recursion_level_from_qubits(info.qubit_count),
        route=info.route or "ifs",
        depth_invariant_fixed_point=info.depth_invariant_fixed_point,
        depth_invariant_confidence=info.depth_invariant_confidence,
        void_encoding_used=False,
        hausdorff_dimension=1.585,  # theoretical
        fractal_graph_nodes=info.qubit_count,
        fractal_graph_edges=0,
        structural_encoding_depth=info.depth,
    )


def _hypothesis_tag_to_enum(tag: str) -> ExperimentTag:
    """Convert a string hypothesis tag to ExperimentTag enum."""
    mapping = {
        "sierpinski_depth_invariant": ExperimentTag.SIERPINSKI_DEPTH_INVARIANT,
        "phi_encoding": ExperimentTag.STRUCTURAL_ENCODING,
        "teleport": ExperimentTag.GRAPH_STATE_TRANSFER,
        "graph_state_transfer": ExperimentTag.GRAPH_STATE_TRANSFER,
        "decoherence_free_subspace": ExperimentTag.DECOHERENCE_FREE_SUBSPACE,
        "entropy_extraction": ExperimentTag.ENTROPY_EXTRACTION,
        "fixed_point_1_over_phi": ExperimentTag.FIXED_POINT_1_OVER_PHI,
        "structural_encoding": ExperimentTag.STRUCTURAL_ENCODING,
    }
    return mapping.get(tag, ExperimentTag.OTHER)


def _circuit_family_to_enum(family: str) -> CircuitFamily:
    """Convert a string circuit family to CircuitFamily enum."""
    mapping = {
        "fractal_walk": CircuitFamily.FRACTAL_WALK,
        "staggered_walk": CircuitFamily.STAGGERED_WALK,
        "coined_walk": CircuitFamily.COINED_WALK,
        "qaoa_style": CircuitFamily.QAOA_STYLE,
        "variational": CircuitFamily.VARIATIONAL,
        "gate_based": CircuitFamily.GATE_BASED,
        "measurement_based": CircuitFamily.MEASUREMENT_BASED,
        "generic": CircuitFamily.GATE_BASED,  # generic gate-based circuits
        "phi_encoding": CircuitFamily.GATE_BASED,
        "teleport": CircuitFamily.GATE_BASED,
    }
    return mapping.get(family, CircuitFamily.UNKNOWN)
    """Map qubit count to Sierpinski recursion level (approximate)."""
    if n_qubits <= 5:
        return 2
    elif n_qubits <= 13:
        return 3
    elif n_qubits <= 25:
        return 4
    elif n_qubits <= 49:
        return 5
    elif n_qubits <= 97:
        return 6
    else:
        return 7


# ---------------------------------------------------------------------------
# Main import logic
# ---------------------------------------------------------------------------

JOB_SOURCES = [
    # (directory, pattern_glob)
]

def find_job_pairs(base_dir: Path):
    """Find all completed IBM job pairs (info + result) in a directory."""
    if not base_dir.exists():
        return []
    pairs = []
    for info_file in sorted(base_dir.glob("*-info.json")):
        # stem includes the full filename without extension: "job-d7l5ovq8ui0s73b60ong-info"
        # We need the job ID without the "-info" suffix
        stem = info_file.stem  # e.g., "job-d7l5ovq8ui0s73b60ong-info"
        job_id = stem[:-5] if stem.endswith("-info") else stem  # strip "-info"
        result_file = base_dir / f"{job_id}-result.json"
        has_result = result_file.exists()
        pairs.append((info_file, result_file if has_result else None))
    return pairs


def import_jobs(dry_run: bool = False, project_filter: str | None = None) -> list[JobInfo]:
    """Import all discovered IBM job pairs into the corpus."""
    sources = [
        Path("D:/Somnath-PROJECT/qasmsierpinski_tmt_phase4s_ibm_kin/"),
        Path("D:/Somnath-PROJECT/Jobs-to-check/"),
        Path("D:/Somnath-PROJECT/Jobs/"),
    ]

    imported = []
    skipped = 0
    failed = 0

    for src_dir in sources:
        if not src_dir.exists():
            print(f"Source dir not found: {src_dir}")
            continue

        pairs = find_job_pairs(src_dir)
        print(f"\n{src_dir.name}: {len(pairs)} job pairs found")

        for info_path, result_path in pairs:
            try:
                job = parse_job_info(info_path, result_path)
                if job is None:
                    skipped += 1
                    continue

                if project_filter and job.project != project_filter:
                    skipped += 1
                    continue

                print(f"  {job.experiment_id}: {job.backend} | {job.shots} shots | "
                      f"{job.qubit_count} qubits | {job.project}/{job.circuit_family} | "
                      f"{job.backend_generation}")

                if not dry_run:
                    record = _write_job_to_corpus(job)
                    saved_id = record.metadata.experiment_id
                    print(f"    -> saved: {saved_id}")

                imported.append(job)

            except Exception as exc:
                print(f"  ERROR {info_path.name}: {exc}")
                failed += 1

    print(f"\nDone. {len(imported)} imported, {skipped} skipped, {failed} failed")
    return imported


def _write_provenance_sidecar(
    job: JobInfo,
    record: HardwareRunRecord | SierpinskiExperimentRecord,
    out_file: Path,
) -> None:
    """Write a provenance sidecar for an imported job."""
    from datetime import datetime, timezone
    exp_id = (
        record.metadata.experiment_id
        if hasattr(record, "metadata")
        else getattr(record, "snapshot_id", job.experiment_id)
    )
    transform_params = {
        "job_id": job.job_id,
        "shots": job.shots,
        "qubit_count": job.qubit_count,
        "backend": job.backend,
        "circuit_family": job.circuit_family,
        "hypothesis_tag": job.hypothesis_tag,
        "route": job.route,
    }
    if job.depth > 0:
        transform_params["depth"] = job.depth
    if job.fidelity is not None:
        transform_params["fidelity"] = job.fidelity
    if job.measurement_counts:
        transform_params["measurement_states"] = len(job.measurement_counts)

    sidecar = ProvenanceSidecar(
        source_project="somnath-import",
        source_artifact_id=job.job_id,
        source_path=job.source_path,
        source_date=job.created[:10] if job.created else "",
        backend=job.backend,
        import_date=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        import_method="import_new_ibm_jobs",
        sensitivity="internal",
        import_type="historical_real",
        transform_chain=[
            TransformStep(
                step_id=0,
                transform_type="extract",
                description=(
                    f"Imported from IBM Quantum job {job.job_id} on {job.backend}. "
                    f"Project={job.project}, family={job.circuit_family}."
                ),
                parameters=transform_params,
                tool="scripts.import_new_ibm_jobs",
            )
        ],
        claims_supported=[],
        linked_files=[job.raw_data_ref] if job.raw_data_ref else [],
    )
    prov_file = out_file.with_suffix(".provenance.json")
    prov_data = _enum_to_value(sidecar.to_dict())
    with open(prov_file, "w", encoding="utf-8") as f:
        json.dump(prov_data, f, indent=2, ensure_ascii=False)


def _write_job_to_corpus(job: JobInfo) -> HardwareRunRecord | SierpinskiExperimentRecord:
    """Write a JobInfo to the appropriate corpus directory."""
    # Determine output directory
    project_map = {
        "sierpinski": "sierpinski",
        "tmt": "tmt",
        "qsg": "qsg",
    }
    proj_dir = project_map.get(job.project, "qsg")
    out_dir = Path(__file__).parent.parent / "imports" / proj_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write artifact
    out_file = out_dir / f"{job.experiment_id}.json"

    if job.project == "sierpinski":
        record = create_sierpinski_record(job)
        data = _sierpinski_to_dict(record)
    else:
        record = create_hardware_run_record(job)
        data = _hw_run_to_dict(record)

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Write provenance sidecar
    _write_provenance_sidecar(job, record, out_file)

    return record


def _enum_to_value(obj: Any) -> Any:
    """Recursively convert all enum.Enum values to their .value strings."""
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _enum_to_value(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_enum_to_value(x) for x in obj]
    return obj


def _sierpinski_to_dict(rec: SierpinskiExperimentRecord) -> dict:
    """Serialize a SierpinskiExperimentRecord to JSON using schema to_dict()."""
    return _enum_to_value(rec.to_dict())


def _hw_run_to_dict(rec: HardwareRunRecord) -> dict:
    """Serialize a HardwareRunRecord to JSON using schema to_dict()."""
    return _enum_to_value(rec.to_dict())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Import new IBM Quantum jobs into GRE corpus")
    parser.add_argument("--dry-run", action="store_true", help="Parse jobs but don't write files")
    parser.add_argument("--project", help="Filter by project (sierpinski, tmt, qsg)")
    args = parser.parse_args()

    print("IBM Quantum Job Importer")
    print("=" * 60)
    imported = import_jobs(dry_run=args.dry_run, project_filter=args.project)
    print(f"\nTotal: {len(imported)} jobs processed")


if __name__ == "__main__":
    main()
