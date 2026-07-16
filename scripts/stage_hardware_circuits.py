#!/usr/bin/env python3
"""Stage hardware-executable QASM circuits and metadata stubs for manual IBM Quantum submission.

Generates QASM + provenance metadata for pascal_mod2, rule90, and hanoi at levels 4 and 5.
Output: staged/hardware_run_plan/{route}-{level}-{backend}.qasm + .metadata.json

Run:
    python scripts/stage_hardware_circuits.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys_path = Path(__file__).parent.parent
import sys
sys.path.insert(0, str(sys_path))

from gre.compiler.compiler import GeometryCompiler
from gre.compiler.emitters.qasm_emitter import QASMEmitter
from gre.compiler.emitters.qiskit_emitter import QiskitCircuitEmitter

warnings.filterwarnings("ignore")


# ---------------------------------------------------------------------------
# Plan definition
# ---------------------------------------------------------------------------

HARDWARE_TARGETS = [
    # (route, level, target_backends)
    ("hanoi", 4, ["ibm_kingston", "ibm_fez"]),
    ("hanoi", 5, ["ibm_kingston", "ibm_fez"]),
    ("pascal_mod2", 4, ["ibm_kingston", "ibm_fez"]),
    ("pascal_mod2", 5, ["ibm_kingston", "ibm_fez"]),
    ("rule90", 4, ["ibm_kingston", "ibm_fez"]),
    ("rule90", 5, ["ibm_kingston", "ibm_fez"]),
]

# Recommended shot count to match existing corpus statistical rigor
# Existing corpus runs used 4096–8192 shots per job
SHOT_COUNT = 8192


# ---------------------------------------------------------------------------
# Circuit generation
# ---------------------------------------------------------------------------

def generate_circuit(route: str, level: int) -> tuple[dict, str, str]:
    """Compile and emit QASM for (route, level).

    Returns (compilation_metadata, qasm_string, qiskit_circuit_repr).
    """
    compiler = GeometryCompiler()
    result = compiler.compile(
        "sierpinski",
        level=level,
        route=route,
        strategies=["staggered"],
        emit_circuits=True,
    )

    qasm_emitter = QASMEmitter()
    qiskit_emitter = QiskitCircuitEmitter()

    qasm_str = qasm_emitter.emit(result, strategy="staggered")
    qc = qiskit_emitter.emit(result, strategy="staggered")

    rd = result.resonance_descriptor
    sg = rd.spectral_gap

    meta = {
        "route": route,
        "level": level,
        "graph_nodes": result.graph.adjacency.shape[0],
        "graph_edges": int(result.graph.adjacency.sum() // 2),
        "circuit_qubits": qc.num_qubits,
        "circuit_depth": qc.depth(),
        "spectral_gap": float(sg) if sg is not None and not np.isnan(sg) else None,
        "eigenvalue_spacing_ratio": float(rd.eigenvalue_spacing_ratio),
        "average_degree": float(rd.average_degree),
        "attractor_label": result.attractor_signature.attractor_label,
        "walk_steps": 20,
        "strategy": "staggered",
        "emit_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return meta, qasm_str, f"QuantumCircuit({qc.num_qubits}q, depth={qc.depth()})"


def write_staged_files(route: str, level: int, backends: list[str], dry_run: bool):
    """Write QASM and metadata stub for each (route, level, backend) combination."""
    meta, qasm_str, qc_repr = generate_circuit(route, level)
    planned_shots = SHOT_COUNT

    for backend in backends:
        stem = f"{route}-L{level}-{backend}"
        out_dir = Path("staged/hardware_run_plan")
        qasm_path = out_dir / f"{stem}.qasm"
        metadata_path = out_dir / f"{stem}.metadata.json"

        if dry_run:
            print(f"  [dry-run] {qasm_path}  ({len(qasm_str):,} chars, {qc_repr})")
            print(f"  [dry-run] {metadata_path}")
            continue

        out_dir.mkdir(parents=True, exist_ok=True)

        # Write QASM
        with open(qasm_path, "w", encoding="utf-8") as f:
            f.write(qasm_str)

        # Write metadata stub for manual submission
        metadata = {
            "submission_stub": True,
            "route": route,
            "level": level,
            "target_backend": backend,
            "planned_shots": planned_shots,
            "hypothesis_tag": "sierpinski_depth_invariant",
            "circuit_family": "fractal_walk",
            "calibration_snapshot_id": _infer_calibration_snapshot(backend),
            "compiler_metadata": meta,
            "manual_submission_fields": {
                "backend": backend,
                "shots": planned_shots,
                "job_tags": [
                    f"route:{route}",
                    f"level:{level}",
                    f"hypothesis:sierpinski_depth_invariant",
                    f"circuit_family:fractal_walk",
                ],
            },
            "expected_lambda2": meta["spectral_gap"],
            "expected_attractor": meta["attractor_label"],
            "notes": (
                f"Submit via: ibm quantum job submit {qasm_path.name} --backend {backend} --shots {planned_shots}\n"
                f"After execution, import via: python scripts/import_new_ibm_jobs.py --source staged_hardware\n"
                f"Expected spectral gap: {meta['spectral_gap']:.6f} (structurally distinct from ifs~0.034)"
                if route == "hanoi" and level == 4
                else (
                    f"Submit via: ibm quantum job submit {qasm_path.name} --backend {backend} --shots {planned_shots}\n"
                    f"After execution, import via: python scripts/import_new_ibm_jobs.py --source staged_hardware"
                )
            ),
        }

        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        print(f"  Wrote {qasm_path}  ({len(qasm_str):,} chars, {qc_repr})")
        print(f"  Wrote {metadata_path}")


def _infer_calibration_snapshot(backend: str) -> str:
    if backend == "ibm_kingston":
        return "cal-ibm-kingston-20260423"
    elif backend == "ibm_fez":
        return "cal-ibm-fez-20260305"
    return ""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Stage QASM circuits for manual IBM submission")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be written")
    args = parser.parse_args()

    print("Staging hardware circuits for manual IBM Quantum submission")
    print(f"Shot count per job: {SHOT_COUNT}")
    print()

    for route, level, backends in HARDWARE_TARGETS:
        print(f"[{route} L{level}]")
        write_staged_files(route, level, backends, dry_run=args.dry_run)

    print()
    print("Staging complete. Review staged/hardware_run_plan/ before manual submission.")
    print()
    print("After execution, add 'staged_hardware' to SOURCES in import_new_ibm_jobs.py")
    print("and run: python scripts/import_new_ibm_jobs.py --source staged_hardware")


if __name__ == "__main__":
    main()
