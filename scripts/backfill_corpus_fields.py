#!/usr/bin/env python3
"""Backfill evidence_class, validation_tier, and backend_generation fields.

Also sets calibration_completeness for all CalibrationSnapshot records.

Run:
    python scripts/backfill_corpus_fields.py
"""

import json
import sys
from pathlib import Path

# ------------------------------------------------------------------
# Per-artifact classification decisions
# ------------------------------------------------------------------

# (artifact_id, evidence_class, validation_tier, backend_generation)
HARDWARE_RUNS = {
    # QSG historical runs
    "qsg-run-042":      ("historical_real", "benchmarked",  "simulator"),
    "qsg-run-043":      ("historical_real", "normalized",   "ibm_eagle"),
    "qsg-run-044":      ("historical_real", "benchmarked",  "ibm_falcon"),
    "qsg-run-lima-001": ("historical_real", "benchmarked",  "ibm_falcon"),
    "qsg-run-manila-001": ("historical_real", "benchmarked", "ibm_falcon"),
    # IBM Quantum real hardware runs
    "ibm-quantum-kingston-teleport-001":   ("historical_real", "benchmarked", "ibm_herron"),
    "ibm-quantum-kingston-teleport-002":   ("historical_real", "benchmarked", "ibm_herron"),
    "ibm-quantum-kingston-teleport-003":   ("historical_real", "benchmarked", "ibm_herron"),
    "ibm-quantum-kingston-near-entropy-001": ("historical_real", "benchmarked", "ibm_herron"),
    "ibm-quantum-fez-er-epr-001":          ("historical_real", "benchmarked", "ibm_herron"),
    "ibm-quantum-fez-sampler-v2-001":      ("historical_real", "benchmarked", "ibm_herron"),
    # Sierpinski experiments
    "sierpinski-level3-ifs":        ("historical_real", "benchmarked", "simulator"),
    "sierpinski-level4-pascal":      ("historical_real", "benchmarked", "simulator"),
    "sierpinski-level4-hanoi":       ("historical_real", "benchmarked", "simulator"),
    "sierpinski-level4-rule90":      ("historical_real", "benchmarked", "simulator"),
    "sierpinski-level4-ibm-kingston-001": ("historical_real", "benchmarked", "ibm_herron"),
    "sierpinski-level5-ifs":         ("historical_real", "benchmarked", "simulator"),
    "sierpinski-level5-pascal":      ("historical_real", "benchmarked", "simulator"),
    "sierpinski-level6-ifs":          ("historical_real", "benchmarked", "simulator"),
    # Simulator / synthetic circuits
    "merkaba-phi-encoding-17q":  ("synthetic_seed", "normalized", "simulator"),
    "merkaba-phi-encoding-27q":  ("synthetic_seed", "normalized", "simulator"),
    "phi-encoding-circuit-5q":    ("synthetic_seed", "normalized", "simulator"),
}

# (snapshot_id, calibration_completeness)
CALIBRATION_SNAPSHOTS = {
    "cal-ibm-perth-20240402":     "physical",
    "cal-ibm-guadalupe-20240418": "physical",
    "cal-ibm-kingston-20260423":  "metadata",
    "cal-ibm-fez-20260305":       "metadata",
}

# Backend generation lookup for auto-fill
BACKEND_GENERATION_BY_PREFIX = {
    "ibm_herron": "ibm_herron",
    "ibmq_qasm":  "simulator",
    "aer_":       "simulator",
    "ibmq_falcon":"ibm_falcon",
    "ibmq_eagle": "ibm_eagle",
    "ibmq_":      "unknown",
    "ibm_":       "unknown",
    "quera_":     "ibm_quera",
}

# Validation tier auto-fill based on metrics present
def infer_validation_tier(data: dict) -> str:
    """Infer validation_tier from presence of metrics."""
    has_fp = data.get("depth_invariant_fixed_point") is not None
    has_phi_dev = data.get("phi_deviation") is not None
    has_score = data.get("sierpinski_score") is not None
    has_fidelity = data.get("fidelity") is not None
    has_lambda2 = data.get("lambda2") is not None
    if has_fp or (has_phi_dev and has_fidelity):
        return "benchmarked"
    if has_fidelity or has_score:
        return "normalized"
    return "raw"


def infer_backend_generation(backend: str) -> str:
    for prefix, gen in BACKEND_GENERATION_BY_PREFIX.items():
        if backend.startswith(prefix):
            return gen
    return "unknown"


def find_artifact_json(imports_dir: Path, artifact_id: str) -> Path | None:
    """Find the JSON file for an artifact by searching all project directories."""
    for project_dir in imports_dir.iterdir():
        if not project_dir.is_dir() or project_dir.name.startswith("_"):
            continue
        candidate = project_dir / f"{artifact_id}.json"
        if candidate.exists():
            return candidate
    return None


def update_hw_run(path: Path, spec: tuple) -> None:
    evidence_class, validation_tier_override, backend_gen = spec
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    changed = False

    if data.get("evidence_class") != evidence_class:
        data["evidence_class"] = evidence_class
        changed = True

    # Only override validation_tier if it's not already set to something higher
    TIER_ORDER = ["raw", "normalized", "benchmarked", "measured"]
    current_tier = data.get("validation_tier", "normalized")
    if validation_tier_override not in TIER_ORDER:
        validation_tier_override = infer_validation_tier(data)
    if TIER_ORDER.index(validation_tier_override) > TIER_ORDER.index(current_tier):
        data["validation_tier"] = validation_tier_override
        changed = True
    elif "validation_tier" not in data:
        data["validation_tier"] = infer_validation_tier(data)
        changed = True

    if data.get("backend_generation") != backend_gen:
        data["backend_generation"] = backend_gen
        changed = True
    elif "backend_generation" not in data:
        data["backend_generation"] = backend_gen
        changed = True

    if changed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  UPDATED {path.relative_to(path.parents[1])}")


def update_calibration(path: Path, completeness: str) -> None:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    changed = False
    if data.get("calibration_completeness") != completeness:
        data["calibration_completeness"] = completeness
        changed = True
    elif "calibration_completeness" not in data:
        data["calibration_completeness"] = completeness
        changed = True

    if changed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  UPDATED {path.relative_to(path.parents[1])}")


def main():
    imports_dir = Path(__file__).parent.parent / "imports"
    print("Backfilling corpus fields...")
    print()

    # Process hardware runs and sierpinski experiments
    hw_updated = 0
    for artifact_id, spec in HARDWARE_RUNS.items():
        path = find_artifact_json(imports_dir, artifact_id)
        if path:
            update_hw_run(path, spec)
            hw_updated += 1
        else:
            print(f"  MISSING: {artifact_id}")

    # Process calibration snapshots
    cal_updated = 0
    for snapshot_id, completeness in CALIBRATION_SNAPSHOTS.items():
        found = False
        for candidate in [
            imports_dir / "calibration" / f"{snapshot_id}.json",
            imports_dir / "tmt" / f"{snapshot_id}.json",
        ]:
            if candidate.exists():
                update_calibration(candidate, completeness)
                cal_updated += 1
                found = True
        if not found:
            print(f"  MISSING CAL: {snapshot_id}")

    # Also handle phi-scaling-empirical-001 which lives in tmt/ but is a calibration snapshot
    phi_scaling = imports_dir / "tmt" / "phi-scaling-empirical-001.json"
    if phi_scaling.exists():
        with open(phi_scaling, encoding="utf-8") as f:
            data = json.load(f)
        changed = False
        if data.get("calibration_completeness") != "metadata":
            data["calibration_completeness"] = "metadata"
            changed = True
        elif "calibration_completeness" not in data:
            data["calibration_completeness"] = "metadata"
            changed = True
        if changed:
            with open(phi_scaling, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"  UPDATED {phi_scaling.relative_to(phi_scaling.parents[1])}")
            cal_updated += 1

    print()
    print(f"Done. {hw_updated} hardware runs, {cal_updated} calibrations processed.")


if __name__ == "__main__":
    main()
