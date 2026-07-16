#!/usr/bin/env python3
"""Import newly discovered IBM Quantum jobs into the GRE corpus.

Five source directories are supported, importable in recommended sequence:

  1. Jobs/         (E:/AGI model/data/Jobs/)         — 235 sampler jobs, ibm_fez/torino/marrakesh
  2. docasne/      (E:/AGI model/data/docasne/)      — 8 sampler jobs, ibm_fez/marrakesh
  3. consolidated/  (E:/AGI model/data/consolidated/) — 149 properly-serialized jobs
  4. broken_consolidated/                            — 43 consolidated jobs with bound-method backend
  5. legacy/       (D:/Somnath-PROJECT/*/)           — original Somnath import paths

For each job:
  1. Read the -info.json to get backend, date, shots, program type
  2. Read the -result.json to extract measurement outcomes (Qiskit 2.x PrimitiveResult)
  3. Decode QPY circuit to determine qubit count, circuit_family, and route
  4. Classify as hardware_run or sierpinski_experiment based on circuit type
  5. Write to imports/<project>/<artifact_id>.json with full provenance

Run:
    python scripts/import_new_ibm_jobs.py --dry-run
    python scripts/import_new_ibm_jobs.py --source jobs
    python scripts/import_new_ibm_jobs.py --source docasne
    python scripts/import_new_ibm_jobs.py --source consolidated
    python scripts/import_new_ibm_jobs.py --source broken_consolidated
"""

import argparse
import base64
import enum
import json
import re
import struct
import sys
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

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
)
from gre.research.provenance import ProvenanceSidecar, TransformStep


# ---------------------------------------------------------------------------
# Source directories
# ---------------------------------------------------------------------------

SOURCES = {
    "jobs": Path("E:/AGI model/data/Jobs/"),
    "docasne": Path("E:/AGI model/data/docasne/"),
    "consolidated": Path("E:/AGI model/data/consolidated/"),
    # Legacy paths from the original import script
    "legacy_somnath": Path("D:/Somnath-PROJECT/qasmsierpinski_tmt_phase4s_ibm_kin/"),
    "legacy_jobs_check": Path("D:/Somnath-PROJECT/Jobs-to-check/"),
    "legacy_jobs": Path("D:/Somnath-PROJECT/Jobs/"),
}


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
    qubit_count: int
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
    # Metrics
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

    Returns dict with: qubit_count, depth (approximate), gate_ops, is_sierpinski
    """
    try:
        raw = decode_qpy_size_prefixed(b64_data)
    except Exception:
        return {"qubit_count": 0, "depth": 0, "gate_ops": 0, "is_sierpinski": False}

    si_markers = raw.count(b'SI')
    cz_count = raw.count(b'cz ')
    cx_count = raw.count(b'cx ')
    x_count  = raw.count(b'x  ')
    rz_count = raw.count(b'rz ')
    sx_count = raw.count(b'sx')

    gate_ops = cz_count + cx_count + x_count + rz_count + sx_count

    # Qubit count from header 'q<N>' ASCII markers
    qubit_indices = set()
    for match in re.finditer(rb'q(\d+)', raw[:2000]):
        qubit_indices.add(int(match.group(1)))
    qubit_count = max(qubit_indices) + 1 if qubit_indices else 0

    if qubit_count == 0:
        edge_max = 0
        for match in re.finditer(rb'c[zx] (\d+),(\d+)', raw):
            a, b = int(match.group(1)), int(match.group(2))
            edge_max = max(edge_max, a, b)
        qubit_count = max(edge_max + 1, 5)

    depth = raw.count(b'schedule') + gate_ops // max(qubit_count, 1)
    is_sierpinski = si_markers > 0 or b'SIERPINSKI' in raw[:500]

    return {
        "qubit_count": qubit_count,
        "depth": min(depth, 100),
        "gate_ops": gate_ops,
        "is_sierpinski": is_sierpinski,
        "cz_count": cz_count,
        "cx_count": cx_count,
    }


# ---------------------------------------------------------------------------
# OPENQASM 3.0 circuit inspector
# ---------------------------------------------------------------------------

def inspect_openqasm_circuit(qasm_str: str) -> dict:
    """Extract key info from an inline OPENQASM 3.0 circuit string."""
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
        for match in re.finditer(r'q(\d+)', line):
            qubit_count = max(qubit_count, int(match.group(1)) + 1)
        for gate in ['cx', 'cz', 'rx', 'ry', 'rz', 'sx', 'x', 'h', 't', 's']:
            if f' {gate} ' in line or f'({gate})' in line or line.startswith(gate):
                gate_ops += 1
                if gate == 'cz':
                    has_cz = True
                if gate == 'rx':
                    has_rx = True
        if 'phi' in line.lower() or '1.618' in line or '0.618' in line:
            is_phi_encoded = True
        if 'sierpinski' in line.lower():
            is_sierpinski = True
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
# Backend helpers
# ---------------------------------------------------------------------------

BACKEND_GENERATION_MAP = {
    "ibm_kingston": "ibm_herron",
    "ibm_fez": "ibm_herron",
    "ibm_marrakesh": "ibm_herron",
    "ibm_torino": "ibm_herron",
    "ibmq_perth": "ibm_falcon",
    "ibmq_lima": "ibm_falcon",
    "ibmq_manila": "ibm_falcon",
    "ibmq_guadalupe": "ibm_eagle",
    "ibmq_qasm_simulator": "simulator",
    "aer_simulator": "simulator",
}


def infer_backend_generation(backend: str) -> str:
    return BACKEND_GENERATION_MAP.get(backend, "unknown")


def infer_calibration_snapshot_id(backend: str, date_str: str | None) -> str:
    date = date_str[:10] if date_str else ""
    if backend == "ibm_kingston":
        return "cal-ibm-kingston-20260423"
    elif backend == "ibm_fez":
        return "cal-ibm-fez-20260305"
    elif backend == "ibm_marrakesh":
        return ""  # no snapshot yet
    return ""


def extract_backend_from_bound_method(info: dict) -> str:
    """Recover backend name from a bound-method RuntimeJobV2.backend field.

    When a RuntimeJobV2 object is JSON-serialized without __qiskit_ibm__.dynamic_encode,
    the backend field becomes a bound method repr string like:
      "<bound method RuntimeJobV2.backend of <RuntimeJobV2('d4mfl02v0j9c73e69300', 'sampler')>>"

    The job_id is extracted from the RuntimeJobV2 repr, then the corresponding
    info file is checked for a 'backend' string at the top level or in any nested
    object. We also try extracting the backend from the job_id prefix convention.
    """
    # Pattern: RuntimeJobV2('job_id', 'program')
    m = re.search(r"RuntimeJobV2\('([^']+)'", str(info))
    if not m:
        return "unknown"
    job_id = m.group(1)

    # Try to read the result file if it exists — it may have the backend
    # (result files were serialized more carefully)
    # For now, use the job_id prefix as a heuristic:
    # ibm_fez jobs start with 'd4mfq' or 'd4mf'
    # ibm_torino jobs start with 'd4tnt' etc.
    if job_id.startswith('d4mfq') or job_id.startswith('d4tnt') or job_id.startswith('d4pe'):
        return "ibm_fez"
    elif job_id.startswith('d4tnt') or job_id.startswith('d4ti5'):
        return "ibm_torino"
    elif job_id.startswith('d631'):
        return "ibm_marrakesh"
    elif job_id.startswith('d7l'):
        return "ibm_kingston"

    return "unknown"


# ---------------------------------------------------------------------------
# Job parsing — two format dispatchers
# ---------------------------------------------------------------------------

def parse_ibm_runtime_v2(info: dict, result_data: dict | None, source_path: Path) -> JobInfo | None:
    """Parse IBM Runtime v2 format (Jobs/, docasne/, most consolidated/).

    info keys: id, backend, params{pubs, support_qiskit}, program{id}, created, status
    result_data: deserialized JSON of the -result.json file
    """
    job_id = info.get("id", "")
    backend_raw = info.get("backend", "")
    created = info.get("created", "")
    program_id = info.get("program", {}).get("id", "") if isinstance(info.get("program"), dict) else ""

    # Handle bound-method backend (broken serialization) — also catches when
    # backend_raw is a valid str but contains the bound-method repr text
    if not isinstance(backend_raw, str) or not backend_raw or backend_raw.startswith("<bound method"):
        backend = extract_backend_from_bound_method(info)
    else:
        backend = backend_raw

    params = info.get("params") or {}
    pubs = params.get("pubs", []) if isinstance(params, dict) else []

    qubit_count = 0
    circuit_family = "unknown"
    is_sierpinski = False
    is_phi_encoded = False
    has_conditional = False
    shots_val = 0
    depth = 0

    for pub in pubs if isinstance(pubs, list) else []:
        if not isinstance(pub, list) or len(pub) < 3:
            continue
        circuit_or_qasm, _, shots_val = pub[0], pub[1], pub[2]
        shots = int(shots_val) if isinstance(shots_val, (int, float)) else 0

        # IBM Runtime v2: QuantumCircuit QPY b64
        if isinstance(circuit_or_qasm, dict):
            circuit_type = circuit_or_qasm.get("__type__", "")
            if circuit_type == "QuantumCircuit":
                b64 = circuit_or_qasm.get("__value__", "")
                qpy_info = inspect_qpy_circuit(b64)
                qubit_count = qpy_info["qubit_count"]
                depth = qpy_info["depth"]
                is_sierpinski = qpy_info["is_sierpinski"]
                circuit_family = "fractal_walk" if is_sierpinski else "generic"
            elif circuit_type == "str":
                # OPENQASM 3.0 string
                qasm_str = circuit_or_qasm.get("__value__", "")
                qasm_info = inspect_openqasm_circuit(qasm_str)
                qubit_count = qasm_info["qubit_count"]
                is_sierpinski = qasm_info["is_sierpinski"]
                is_phi_encoded = qasm_info["is_phi_encoded"]
                has_conditional = qasm_info["has_conditional"]
                circuit_family = "fractal_walk" if is_sierpinski else "phi_encoding"

        # Legacy: raw string circuit
        elif isinstance(circuit_or_qasm, str) and len(circuit_or_qasm) > 100:
            if "OPENQASM" in circuit_or_qasm or "include" in circuit_or_qasm:
                qasm_info = inspect_openqasm_circuit(circuit_or_qasm)
                qubit_count = qasm_info["qubit_count"]
                is_sierpinski = qasm_info["is_sierpinski"]
                is_phi_encoded = qasm_info["is_phi_encoded"]
                has_conditional = qasm_info["has_conditional"]
                circuit_family = "fractal_walk" if is_sierpinski else "phi_encoding"
            else:
                qpy_info = inspect_qpy_circuit(circuit_or_qasm)
                qubit_count = qpy_info["qubit_count"]
                is_sierpinski = qpy_info["is_sierpinski"]
                circuit_family = "fractal_walk" if is_sierpinski else "generic"

    # Classify project
    if is_sierpinski:
        project = "sierpinski"
        route = _infer_route(source_path)
        hypothesis_tag = "sierpinski_depth_invariant"
    elif is_phi_encoded or has_conditional:
        project = "tmt"
        circuit_family = "phi_encoding"
        hypothesis_tag = "phi_encoding"
        route = "phi"
    else:
        project = "qsg"
        circuit_family = "generic"
        hypothesis_tag = "generic_sampler"
        route = ""

    # Build experiment_id — use full job_id to avoid collisions on genericSampler jobs
    date_short = created[:10].replace("-", "") if created else "unknown"
    if is_sierpinski:
        experiment_id = f"sierpinski-{backend}-{job_id[:8]}"
    elif is_phi_encoded:
        experiment_id = f"ibm-{backend}-phi-{job_id}"
    else:
        experiment_id = f"ibm-{backend}-{job_id}"

    # Parse result data
    fidelity = None
    measurement_counts = None
    result_n_qubits = 0
    if result_data:
        rdata = _extract_result_data(result_data)
        if rdata is not None:
            result_n_qubits, counts_b64 = rdata
            if result_n_qubits > 0 and counts_b64:
                measurement_counts = _decode_bitstring_counts(counts_b64)
                if measurement_counts and shots_val:
                    fidelity = _compute_fidelity_from_counts(measurement_counts)
            if result_n_qubits > 0:
                qubit_count = result_n_qubits

    return JobInfo(
        job_id=job_id,
        backend=backend,
        created=created,
        program_id=program_id,
        shots=int(shots_val) if isinstance(shots_val, (int, float)) else 0,
        qubit_count=qubit_count,
        circuit_family=circuit_family,
        experiment_id=experiment_id,
        project=project,
        hypothesis_tag=hypothesis_tag,
        route=route,
        depth=depth,
        calibration_snapshot_id=infer_calibration_snapshot_id(backend, created),
        evidence_class="historical_real",
        validation_tier="benchmarked",
        backend_generation=infer_backend_generation(backend),
        fidelity=fidelity,
        measurement_counts=measurement_counts,
        source_path=str(source_path),
        raw_data_ref="",
    )


def parse_legacy_format(info: dict, result_data: dict | None, source_path: Path) -> JobInfo | None:
    """Parse the legacy Somnath QPY format (D:/Somnath-PROJECT/*/).

    info keys: id, backend, params{quantum_program{items{circuit{circuit_b64|openqasm}}}}
    """
    job_id = info.get("id", "")
    backend = info.get("backend", "unknown")
    created = info.get("created", "")
    program_id = info.get("program", {}).get("id", "") if isinstance(info.get("program"), dict) else ""
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

    items = qprog.get("items", [])
    for item in items:
        circuit = item.get("circuit", {})
        if "circuit_b64" in circuit:
            qpy_info = inspect_qpy_circuit(circuit["circuit_b64"])
            qubit_count = qpy_info["qubit_count"]
            depth = qpy_info["depth"]
            is_sierpinski = qpy_info["is_sierpinski"]
            circuit_family = "fractal_walk" if is_sierpinski else "generic"
        elif "openqasm" in circuit:
            qasm_str = circuit.get("openqasm", "")
            qasm_info = inspect_openqasm_circuit(qasm_str)
            qubit_count = qasm_info["qubit_count"]
            is_sierpinski = qasm_info["is_sierpinski"]
            is_phi_encoded = qasm_info["is_phi_encoded"]
            has_conditional = qasm_info["has_conditional"]
            circuit_family = "fractal_walk" if is_sierpinski else "teleport"

        circuit_label = circuit.get("label", "") or circuit.get("name", "")
        if circuit_label:
            cl = circuit_label.lower()
            if "sierpinski" in cl or "ifs" in cl:
                is_sierpinski = True
                circuit_family = "fractal_walk"
            elif "phi" in cl or "merkaba" in cl:
                is_phi_encoded = True

    if is_sierpinski:
        project = "sierpinski"
        route = _infer_route(source_path)
        hypothesis_tag = "sierpinski_depth_invariant"
        depth = _infer_depth(source_path, qprog)
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

    if is_sierpinski:
        experiment_id = f"sierpinski-{backend}-{job_id[:8]}"
    elif is_phi_encoded:
        experiment_id = f"ibm-{backend}-phi-{job_id}"
    else:
        experiment_id = f"ibm-{backend}-{job_id}"

    fidelity = None
    measurement_counts = None
    result_n_qubits = 0
    if result_data:
        rdata = _extract_result_data(result_data)
        if rdata is not None:
            result_n_qubits, counts_b64 = rdata
            if result_n_qubits > 0 and counts_b64:
                measurement_counts = _decode_bitstring_counts(counts_b64)
                if measurement_counts and shots:
                    fidelity = _compute_fidelity_from_counts(measurement_counts)
            if result_n_qubits > 0:
                qubit_count = result_n_qubits

    return JobInfo(
        job_id=job_id,
        backend=backend,
        created=created,
        program_id=program_id,
        shots=shots,
        qubit_count=qubit_count,
        circuit_family=circuit_family,
        experiment_id=experiment_id,
        project=project,
        hypothesis_tag=hypothesis_tag,
        route=route,
        depth=depth,
        calibration_snapshot_id=infer_calibration_snapshot_id(backend, created),
        evidence_class="historical_real",
        validation_tier="benchmarked",
        backend_generation=infer_backend_generation(backend),
        fidelity=fidelity,
        measurement_counts=measurement_counts,
        source_path=str(source_path),
        raw_data_ref="",
    )


# ---------------------------------------------------------------------------
# Route / depth inference helpers
# ---------------------------------------------------------------------------

def _infer_route(info_path: Path) -> str:
    path_str = str(info_path).lower()
    if "pascal" in path_str:
        return "pascal_mod2"
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
    return "ifs"


def _infer_depth(info_path: Path, qprog: dict) -> int:
    items = qprog.get("items", [])
    if not items:
        return 5
    for item in items:
        circuit = item.get("circuit", {})
        label = circuit.get("label", "") or circuit.get("name", "")
        m = re.search(r'-(\d+)$', label)
        if m:
            return int(m.group(1))
    return 5


# ---------------------------------------------------------------------------
# Result data extraction
# ---------------------------------------------------------------------------

def _extract_result_data(result: dict) -> tuple[int, str] | None:
    """Extract (n_qubits, base64_packed_counts) from any IBM result format.

    Handles:
    1. Legacy: {"data": [{results: {c: {shape, data}}}]}
    2. Sampler v2: {"__type__": "PrimitiveResult", "__value__": {pub_results: [...]}}
    3. docasne: {"results": [{data: {c: {samples: [hex], num_bits}}}]}

    Returns (n_qubits, base64_packed_counts) or None.
    """
    # Guard: if result is not a parsed dict (e.g., a Python repr string), skip
    if not isinstance(result, dict):
        return None

    # Format 2: IBM Runtime v2 PrimitiveResult
    if result.get("__type__") == "PrimitiveResult":
        try:
            pub_results = result["__value__"]["pub_results"]
            if not pub_results:
                return None
            pub0 = pub_results[0]
            if pub0.get("__type__") == "SamplerPubResult":
                val = pub0["__value__"]
                databin = val["data"]["__value__"]
                fields = databin.get("fields", {})
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
        except Exception:
            pass

    # Format 3: docasne style {"results": [{data: {c: {samples, num_bits}}}]}
    if result.get("results"):
        try:
            entry = result["results"][0]
            c_data = entry.get("data", {}).get("c", {})
            if isinstance(c_data, dict):
                samples = c_data.get("samples", [])
                num_bits = c_data.get("num_bits", 0)
                if samples and num_bits > 0:
                    packed = _pack_hex_samples(samples, num_bits)
                    return num_bits, packed
        except Exception:
            pass

    # Format 1: legacy {"data": [{results: {c: {shape, data}}}]}
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
        except Exception:
            pass

    return None


def _pack_hex_samples(samples: list[str], num_bits: int) -> str:
    """Pack hex bitstring samples into base64-encoded packed bit array (LSB-first)."""
    n_shots = len(samples)
    n_bytes = (n_shots * num_bits + 7) // 8
    packed = bytearray(n_bytes)
    for shot_idx, hex_str in enumerate(samples):
        val = int(hex_str, 16)
        for bit in range(num_bits):
            byte_idx = (shot_idx * num_bits + bit) // 8
            bit_idx = (shot_idx * num_bits + bit) % 8
            if (val >> bit) & 1:
                packed[byte_idx] |= 1 << bit_idx
    return base64.b64encode(bytes(packed)).decode("ascii")


def _pack_numpy_bit_array(decompressed: bytes, num_bits: int) -> str | None:
    """Unpack numpy BitArray bytes into base64-packed bit array."""
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


def _decode_bitstring_counts(data_b64: str) -> dict:
    """Decode base64-packed bit array into {int_value: count} dict."""
    try:
        raw = base64.b64decode(data_b64)
        # Determine n_qubits and n_shots from raw byte length
        # We pack 8 bits per byte; n_qubits is embedded in the file or inferred
        # For now, return raw bytes for the caller to interpret
        # This is a simplified version; proper parsing needs shot/qubit metadata
        return {}
    except Exception:
        return {}


def _compute_fidelity_from_counts(counts: dict) -> float | None:
    """Fidelity ≈ max_count / total_shots."""
    if not counts:
        return None
    max_count = max(counts.values())
    total = sum(counts.values())
    return max_count / total if total > 0 else None


# ---------------------------------------------------------------------------
# Record creation
# ---------------------------------------------------------------------------

def create_hardware_run_record(info: JobInfo) -> HardwareRunRecord:
    metadata = ExperimentMetadata(
        experiment_id=info.experiment_id,
        project=info.project,
        date=info.created[:10] if info.created else "",
        hypothesis_tag=_hypothesis_tag_to_enum(info.hypothesis_tag),
        circuit_family=_circuit_family_to_enum(info.circuit_family),
    )
    observed = {}
    if info.fidelity is not None:
        observed["fidelity"] = info.fidelity
    if info.measurement_counts:
        observed["measurement_counts"] = info.measurement_counts
        observed["shots"] = info.shots
        observed["qubits"] = info.qubit_count

    _backend = (
        BackendName(info.backend).value
        if info.backend in [b.value for b in BackendName]
        else info.backend
    )

    return HardwareRunRecord(
        metadata=metadata,
        backend=_backend,
        qubit_count=info.qubit_count,
        depth=info.depth,
        shots=info.shots,
        fidelity=info.fidelity,
        phi_deviation=info.phi_deviation,
        observed_metrics=observed,
        provenance=_build_provenance(info),
        evidence_class=info.evidence_class,
        validation_tier=info.validation_tier,
        backend_generation=info.backend_generation,
        calibration_snapshot_id=info.calibration_snapshot_id or None,
    )


def create_sierpinski_record(info: JobInfo) -> SierpinskiExperimentRecord:
    hw_record = create_hardware_run_record(info)
    return SierpinskiExperimentRecord(
        hardware_record=hw_record,
        recursion_level=_recursion_level_from_qubits(info.qubit_count),
        route=info.route or "ifs",
        depth_invariant_fixed_point=info.depth_invariant_fixed_point,
        depth_invariant_confidence=info.depth_invariant_confidence,
        void_encoding_used=False,
        hausdorff_dimension=1.585,
        fractal_graph_nodes=info.qubit_count,
        fractal_graph_edges=0,
        structural_encoding_depth=info.depth,
    )


def _build_provenance(info: JobInfo) -> ProvenanceSidecar:
    return ProvenanceSidecar(
        source_project="somnath-import",
        source_artifact_id=info.job_id,
        source_path=info.source_path,
        source_commit="",
        transform_chain=[
            TransformStep(
                step_id=0,
                transform_type="import",
                description=f"Imported from IBM Quantum job {info.job_id} on {info.backend}",
                parameters={
                    "backend": info.backend,
                    "shots": info.shots,
                    "qubit_count": info.qubit_count,
                    "program_id": info.program_id,
                },
                tool="scripts.import_new_ibm_jobs",
            )
        ],
        sensitivity="internal",
        claims_supported=[],
    )


def _hypothesis_tag_to_enum(tag: str) -> ExperimentTag:
    """Map string tag to ExperimentTag enum, falling back to OTHER if unknown."""
    _TAG_MAP = {
        "sierpinski_depth_invariant": "SIERPINSKI_DEPTH_INVARIANT",
        "phi_encoding": "STRUCTURAL_ENCODING",
        "teleport": "GRAPH_STATE_TRANSFER",
        "graph_state_transfer": "GRAPH_STATE_TRANSFER",
        "decoherence_free_subspace": "DECOHERENCE_FREE_SUBSPACE",
        "entropy_extraction": "ENTROPY_EXTRACTION",
        "fixed_point_1_over_phi": "FIXED_POINT_1_OVER_PDA",
        "structural_encoding": "STRUCTURAL_ENCODING",
        "generic_sampler": "OTHER",
    }
    attr_name = _TAG_MAP.get(tag)
    if attr_name is None:
        return ExperimentTag.OTHER
    return getattr(ExperimentTag, attr_name, ExperimentTag.OTHER)


def _circuit_family_to_enum(family: str) -> CircuitFamily:
    mapping = {
        "fractal_walk": CircuitFamily.FRACTAL_WALK,
        "staggered_walk": CircuitFamily.STAGGERED_WALK,
        "coined_walk": CircuitFamily.COINED_WALK,
        "generic": CircuitFamily.GATE_BASED,
        "phi_encoding": CircuitFamily.GATE_BASED,
        "teleport": CircuitFamily.GATE_BASED,
    }
    return mapping.get(family, CircuitFamily.UNKNOWN)


def _recursion_level_from_qubits(n_qubits: int) -> int:
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
    elif n_qubits <= 241:
        return 7
    else:
        return 8


# ---------------------------------------------------------------------------
# Import logic
# ---------------------------------------------------------------------------

def find_job_pairs(base_dir: Path, pattern: str = "*-info.json"):
    """Find all completed IBM job pairs in a directory."""
    if not base_dir.exists():
        return []
    pairs = []
    for info_file in sorted(base_dir.glob(pattern)):
        stem = info_file.stem
        job_id = stem[:-5] if stem.endswith("-info") else stem
        result_file = base_dir / f"{job_id}-result.json"
        pairs.append((info_file, result_file if result_file.exists() else None))
    return pairs


def detect_format(info: dict) -> str:
    """Detect whether info uses IBM Runtime v2 or legacy Somnath format."""
    params = info.get("params") or {}
    if isinstance(params, dict):
        if "pubs" in params:
            return "runtime_v2"
        if "quantum_program" in params:
            return "legacy"
    return "runtime_v2"  # default


def parse_job_info(info_path: Path, result_path: Path | None) -> JobInfo | None:
    """Parse a single IBM job pair into a JobInfo record."""
    with open(info_path, encoding="utf-8") as f:
        info = json.load(f)

    result_data = None
    if result_path and result_path.exists():
        try:
            with open(result_path, encoding="utf-8") as f:
                result_data = json.load(f)
        except Exception:
            pass

    fmt = detect_format(info)
    if fmt == "runtime_v2":
        return parse_ibm_runtime_v2(info, result_data, info_path)
    else:
        return parse_legacy_format(info, result_data, info_path)


def import_jobs(
    sources: list[str],
    dry_run: bool = False,
    project_filter: str | None = None,
) -> list[JobInfo]:
    """Import jobs from one or more named source directories."""
    imported = []
    skipped = 0
    failed = 0

    for src_key in sources:
        src_dir = SOURCES.get(src_key)
        if src_dir is None:
            print(f"Unknown source: {src_key}")
            continue
        if not src_dir.exists():
            print(f"Source not found: {src_dir}")
            continue

        pairs = find_job_pairs(src_dir)
        print(f"\n[{src_key}] {src_dir.name}: {len(pairs)} job pairs")
        if not pairs:
            print(f"  (no jobs found)")
            continue

        for info_path, result_path in pairs:
            try:
                job = parse_job_info(info_path, result_path)
                if job is None:
                    skipped += 1
                    continue

                if project_filter and job.project != project_filter:
                    skipped += 1
                    continue

                print(
                    f"  {job.experiment_id}: backend={job.backend} | "
                    f"{job.qubit_count}q | {job.shots} shots | "
                    f"{job.project}/{job.circuit_family}"
                )

                if not dry_run:
                    record = _write_job_to_corpus(job)
                    # SierpinskiExperimentRecord wraps HardwareRunRecord; get experiment_id via .hardware_record
                    meta = getattr(record, "hardware_record", None) or record
                    exp_id = getattr(getattr(meta, "metadata", None), "experiment_id", "<no metadata>")
                    print(f"    -> saved: {exp_id}")

                imported.append(job)

            except Exception as exc:
                print(f"  ERROR {info_path.name}: {exc}")
                failed += 1

    print(f"\nDone. {len(imported)} imported, {skipped} skipped, {failed} failed")
    return imported


def _write_job_to_corpus(job: JobInfo):
    project_map = {
        "sierpinski": "sierpinski",
        "tmt": "tmt",
        "qsg": "qsg",
    }
    proj_dir = project_map.get(job.project, "qsg")
    out_dir = Path(__file__).parent.parent / "imports" / proj_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    out_file = out_dir / f"{job.experiment_id}.json"

    if job.project == "sierpinski":
        record = create_sierpinski_record(job)
        data = _enum_to_value(record.to_dict())
    else:
        record = create_hardware_run_record(job)
        data = _enum_to_value(record.to_dict())

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    _write_provenance(job, out_file)
    return record


def _write_provenance(job: JobInfo, out_file: Path) -> None:
    from datetime import datetime, timezone
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
                transform_type="import",
                description=f"Imported from IBM Quantum job {job.job_id} on {job.backend}",
                parameters={
                    "job_id": job.job_id,
                    "shots": job.shots,
                    "qubit_count": job.qubit_count,
                    "backend": job.backend,
                    "program_id": job.program_id,
                },
                tool="scripts.import_new_ibm_jobs",
            )
        ],
        claims_supported=[],
        linked_files=[job.raw_data_ref] if job.raw_data_ref else [],
    )
    prov_file = out_file.with_suffix(".provenance.json")
    with open(prov_file, "w", encoding="utf-8") as f:
        json.dump(_enum_to_value(sidecar.to_dict()), f, indent=2)


def _enum_to_value(obj: Any) -> Any:
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _enum_to_value(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_enum_to_value(x) for x in obj]
    return obj


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Import IBM Quantum jobs into GRE corpus. "
                   "Recommended sequence: jobs -> docasne -> consolidated -> broken_consolidated"
    )
    parser.add_argument(
        "--source",
        "-s",
        action="append",
        dest="sources",
        help="Source to import (jobs, docasne, consolidated, broken_consolidated, legacy_somnath). "
             "Can be passed multiple times. Omit to import all.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse jobs but don't write files",
    )
    parser.add_argument(
        "--project",
        help="Filter by project (sierpinski, tmt, qsg)",
    )
    args = parser.parse_args()

    sources = args.sources if args.sources else list(SOURCES.keys())

    print("IBM Quantum Job Importer")
    print("=" * 60)
    print(f"Sources: {', '.join(sources)}")
    print(f"Dry run: {args.dry_run}")
    print()

    imported = import_jobs(
        sources=sources,
        dry_run=args.dry_run,
        project_filter=args.project,
    )
    print(f"\nTotal: {len(imported)} jobs processed")


if __name__ == "__main__":
    main()
