# GRE Research Corpus — Evidence Taxonomy

**Document version**: 1.0
**Corpus state**: 27 artifacts across 6 projects
**Last updated**: 2026-07-14

---

## Overview

The GRE research corpus mixes three fundamentally different kinds of evidence:

| Term | Definition |
|------|------------|
| **Artifact** | Any structured record in the corpus (hardware run, Sierpinski experiment, calibration snapshot) |
| **Evidence class** | What kind of thing the artifact *is* — real execution, synthetic reference, or derived summary |
| **Validation tier** | How *processed* the artifact's metrics are — raw output, normalized, benchmarked, or measured |
| **Calibration completeness** | Whether physical decoherence data (T1/T2/readout) is attached |

These four axes are orthogonal. A `historical_real` artifact can be `raw` or `benchmarked`. A `synthetic_seed` can be `normalized` or `benchmarked`. The axes describe *different things* and must not be conflated.

---

## Evidence Classes

### `historical_real`

**Definition**: Recorded data from an actual execution on quantum hardware or simulator, without人为干预 to the results.

**Includes**:
- Hardware runs on IBM Quantum backends (real chip or QASM/Aer simulator)
- Sierpinski fractal experiments on any backend
- Calibration snapshots captured from live hardware
- Raw result files (QPY result arrays, measurement shots)

**Excludes**:
- Circuit definitions without execution results
- Post-hoc analyses that summarize other artifacts
- Manually constructed reference structures

**Discriminator**: The artifact contains *observed* metrics from an actual run. If `shots > 0` and `backend` is set, it is almost certainly `historical_real`.

```
historical_real examples:
  - ibm-quantum-kingston-teleport-001 (shots=4096, fidelity=0.847, real hardware)
  - sierpinski-level6-ifs (shots=2048, depth_invariant_fixed_point=0.616, real hardware)
  - cal-ibm-guadalupe-20240418 (T1/T2 times measured on real hardware)
```

### `synthetic_seed`

**Definition**: A generated reference structure or circuit definition used as a seed for further analysis, but not itself executed on hardware.

**Includes**:
- QASM circuit files without corresponding execution results
- Manually constructed reference graphs or geometries
- Derived circuit definitions that serve as "canonical" examples
- Phi-encoding circuits that are theoretical/reference only

**Discriminator**: `shots = 0` (no execution) OR `fidelity = null` AND the artifact is a circuit definition or structural reference. Also: `observed_metrics = {}` (empty).

```
synthetic_seed examples:
  - merkaba-phi-encoding-17q (shots=0, fidelity=null, QASM circuit definition)
  - phi-encoding-circuit-5q (shots=0, fidelity=null, OPENQASM 3.0 circuit)
```

### `derived_summary`

**Definition**: A post-hoc analysis, summary, or interpretation that synthesizes one or more other artifacts.

**Includes**:
- Statistical aggregates of multiple runs
- Theoretical calculations that cite prior artifacts
- Summary documents that consolidate findings from a campaign
- Cross-experiment comparisons

**Discriminator**: The artifact's `provenance.transform_chain` contains a step with `transform_type = "aggregate"`, `"summary"`, or `"analyze"`, AND the artifact references other artifacts as inputs.

```
derived_summary examples:
  - A paper_summary artifact that aggregates multiple hardware runs
  - A cross-backend comparison that builds on individual run records
```

---

## Validation Tiers

Validation tier describes how *processed* an artifact's metrics are. Higher tiers subsume lower tiers — a `benchmarked` artifact has already been normalized, etc.

### `raw`

**Definition**: Unprocessed output directly from hardware/software with original field names and formats.

**Requires**:
- Original output format preserved
- No field normalization applied
- No theoretical comparison made

**Indicator**: The artifact was imported with minimal transformation. `provenance.transform_chain` is empty or contains only `extract` steps.

### `normalized`

**Definition**: Field names, types, and formats standardized. Data is self-consistent and machine-readable.

**Requires**:
- All field names match canonical GRE schema
- Types are correct (floats are floats, ints are ints, not strings)
- Backend names use canonical form (`ibmq_perth`, not `ibm_perth`)
- Missing fields have appropriate null/empty values

**Indicator**: The artifact has been through `normalizers.py` or equivalent. `validation_tier = "normalized"`.

### `benchmarked`

**Definition**: Metrics compared against theoretical predictions, baselines, or prior art. The data is not just readable but *interpreted*.

**Requires**:
- At least one of: `phi_deviation`, `depth_invariant_fixed_point`, `sierpinski_score`, or `fidelity`
- Comparison to a theoretical value (e.g., 1/φ ≈ 0.618, Sierpinski Hausdorff dimension ≈ 1.585)
- Metrics are physically meaningful, not just numerical

**Indicator**: `depth_invariant_fixed_point` within 0.01 of 1/φ, OR `phi_deviation` computed relative to 0.618, OR `sierpinski_score` computed from experiment data.

### `measured`

**Definition**: Physically measured quantities obtained with calibrated instruments. The highest confidence tier.

**Requires**:
- Calibration data from physical instruments (T1, T2, gate fidelity via randomized benchmarking, etc.)
- Not derived from circuit execution output
- Traceable to measurement equipment or validated calibration procedures

**Indicator**: `calibration_completeness = "physical"` on the linked CalibrationSnapshot. For hardware runs: linked to a calibration snapshot with T1/T2 data.

**Current corpus status**: No artifacts currently achieve `measured` tier — all have `calibration_completeness` at `metadata` or `absent` level. This is the P0 gap.

---

## Calibration Completeness

Calibration completeness applies to **CalibrationSnapshot** records and describes how much physical hardware calibration data is present.

### `physical`

**Definition**: Full T1, T2, readout assignment fidelity, gate errors, qubit frequencies, and connectivity available.

**Fields present**: `t1_times`, `t2_times`, `readout_errors`, `gate_errors`, `qubit_freqs`, `readouts`, `connectivity`

**Use case**: Reproducibility assessment, noise characterization, decoherence modeling.

```
current corpus: cal-ibm-perth-20240402, cal-ibm-guadalupe-20240418
```

### `metadata`

**Definition**: Backend identity, timestamp, and configuration metadata available. Physical calibration quantities (T1/T2) not available.

**Fields present**: `backend`, `timestamp`, optionally `notes`. All physical calibration fields are empty dicts.

**Use case**: Backend identification, approximate noise floor estimation, cross-run comparison on same backend.

```
current corpus: cal-ibm-kingston-20260423, cal-ibm-fez-20260305
```

### `absent`

**Definition**: No calibration data available or could not be retrieved.

**Fields present**: None of the physical calibration fields.

**Use case**: Historical records where calibration was not captured; automatically assigned to any calibration snapshot with empty physical fields.

---

## Backend Generations

`backend_generation` describes which hardware generation or class the backend belongs to.

| Generation | Backends | Era | Qubits |
|-----------|----------|-----|--------|
| `ibm_herron` | ibm_fez, ibm_kingston | 2023-2026 | 100+ |
| `ibm_eagle` | ibmq_guadalupe (H1) | 2021 | 65 |
| `ibm_falcon` | ibmq_perth, ibmq_lima, ibmq_manila | 2020-2021 | 27 |
| `simulator` | ibmq_qasm_simulator, aer_simulator | N/A | any |
| `ibm_quera` | quera_ae | varies | varies |
| `unknown` | Cannot be determined | N/A | N/A |

**Generation affects expected fidelity ranges**: Heron backends typically achieve higher fidelity than Falcon/Eagle. Expected real hardware fidelity range by generation:

- Heron: 0.79-0.87 (current corpus observations)
- Eagle: 0.80-0.86
- Falcon: 0.79-0.85
- Simulator: 0.87-0.95

---

## Quality Gate: Measured-Tier Ready

An artifact is **measured-tier ready** when ALL of the following are true:

1. **Provenance exists** — `*.provenance.json` sidecar file present
2. **At least one metric exists** — `fidelity`, `phi_deviation`, `sierpinski_score`, or `depth_invariant_fixed_point` is non-null
3. **Backend is normalized** — No mixed naming (`ibm_perth` vs `ibmq_perth` on the same backend)
4. **Calibration completeness at least `metadata`** — Non-simulator artifacts have a `calibration_snapshot_id` linking to a calibration snapshot with `calibration_completeness` ≠ `absent`

**Run the quality gate**:
```bash
python -m gre.research.corpus_report --verbose
# Look for "Quality Gate: Measured-Tier Ready" section
```

**Current status**: 22/27 artifacts are measured-tier ready. The 5 not-ready are all calibration metadata records (which don't execute on hardware and don't have execution metrics) plus `phi-scaling-tmt-001` which is its own calibration reference.

---

## Calibration Linking Rules

Every non-simulator hardware run should link to a calibration snapshot via `calibration_snapshot_id`.

**Rule 1**: If a run executed on a specific date, link to the calibration snapshot with the closest prior timestamp on the same backend.

**Rule 2**: If no calibration snapshot exists for that backend, link to the closest-generationally similar backend (e.g., `ibmq_lima` → `ibmq_guadalupe` as both are Falcon-era).

**Rule 3**: If no calibration is available at all, set `calibration_snapshot_id = null` and the quality gate will flag it. Do NOT fabricate calibration data.

**Rule 4**: Simulators (`ibmq_qasm_simulator`, `aer_simulator`) do not require calibration linking.

---

## Evidence Class Decision Tree

```
Is this artifact an actual execution on hardware or simulator?
├── NO → Is it a derived summary/analysis of other artifacts?
│       ├── YES → derived_summary
│       └── NO → Is it a circuit/reference definition without execution?
│               ├── YES → synthetic_seed
│               └── NO → synthetic_seed (default for unclear cases)
└── YES → Is the execution on real hardware (shots > 0, backend ≠ simulator)?
          ├── YES → historical_real
          └── NO (simulator execution) → historical_real (simulator runs count as real executions)
```

---

## Validation Tier Decision Tree

```
Does the artifact have metrics compared to theory?
├── YES → Is it physically measured (T1/T2 from instruments)?
│       ├── YES → measured
│       └── NO → benchmarked
└── NO → Has field normalization been applied?
        ├── YES → normalized
        └── NO → raw
```

---

## Current Corpus Summary

| Evidence Class | Count | Artifacts |
|---------------|-------|-----------|
| historical_real | 19 | All QSG, IBM Quantum, and calibration records |
| synthetic_seed | 3 | merkaba-phi-encoding-17q, merkaba-phi-encoding-27q, phi-encoding-circuit-5q |
| derived_summary | 0 | None yet — future planned for cross-run analyses |

| Validation Tier | Count | Notes |
|-----------------|-------|-------|
| raw | 0 | — |
| normalized | 3 | synthetic circuits only |
| benchmarked | 19 | All historical_real executions |
| measured | 0 | P0 gap — requires physical calibration data |

| Calibration Completeness | Count | Notes |
|-------------------------|-------|-------|
| physical | 2 | cal-ibm-perth-20240402, cal-ibm-guadalupe-20240418 |
| metadata | 2 | cal-ibm-kingston-20260423, cal-ibm-fez-20260305 |
| absent | 0 | All calibration records have at least metadata |

| Backend Generation | Count | Notes |
|-------------------|-------|-------|
| ibm_herron | 7 | ibm_kingston + ibm_fez runs |
| ibm_falcon | 3 | ibmq_lima, ibmq_manila, qsg-run-044 |
| ibm_eagle | 1 | qsg-run-043 (ibmq_guadalupe) |
| simulator | 11 | QASM simulator runs |
| unknown | 1 | phi-scaling-tmt-001 (metadata calibration) |

---

## Physical Calibration Upgrade

A `metadata`-level calibration snapshot can be upgraded to `physical` when T1/T2 data becomes available from IBM Quantum API or saved fixtures.

### When to Upgrade

Upgrade when you obtain an IBM Quantum API calibration response payload containing:
- `t1_times`: non-empty dict of T1 coherence times (in µs) keyed by qubit index
- `t2_times`: non-empty dict of T2 coherence times (in µs) keyed by qubit index

### How to Upgrade

```python
from gre.research import calibration_fetch

# Load the existing metadata snapshot
existing = calibration_fetch.load_calibration_from_file("imports/calibration/cal-ibm-kingston-20260423.json")

# Parse the new physical payload (from IBM API or saved fixture)
new_payload = calibration_fetch.parse_ibm_calibration_payload(
    saved_ibm_api_response,
    source_ref="/path/to/ibm_api_calibration_response.json"
)

# Upgrade in place — returns UpgradeResult
result = calibration_fetch.upgrade_calibration_snapshot(existing, new_payload)
print(result.message)
# → "Upgraded ibm_kingston from metadata to physical. Fields updated: t1_times, t2_times, ..."

# Save the upgraded snapshot back
import json
with open("imports/calibration/cal-ibm-kingston-20260423.json", "w") as f:
    json.dump(existing, f, indent=2)
```

### Upgrade Decision Rules

| Existing State | New Data | Action |
|---------------|----------|--------|
| `metadata` | `physical` | Upgrade fields, set `calibration_completeness = physical` |
| `physical` | `physical` | Merge — keep whichever has more populated fields |
| `physical` | `metadata` | No change (conservative; use `allow_downgrade=True` to override) |
| `metadata` | `metadata` | No change |
| `absent` | `physical` | Upgrade to physical |

### Safety Invariant

`upgrade_calibration_snapshot` **raises `ValueError`** if new_data claims to be physical (`calibration_completeness = "physical"`) but is missing `t1_times` or `t2_times`. This prevents corrupt payloads from silently creating incomplete records.

```python
# This raises — payload claims physical but has no T1 data
new_payload = {"backend": "ibm_kingston", "calibration_completeness": "physical", "t2_times": {...}}
result = calibration_fetch.upgrade_calibration_snapshot(existing, new_payload)
# → ValueError: new_data must contain non-empty t1_times AND t2_times to upgrade
```

### Resolving Multiple Snapshots

When multiple calibration snapshots exist for the same backend (e.g., from different dates), use `resolve_best_snapshot`:

```python
from gre.research import calibration_fetch

snapshots = calibration_fetch.load_calibration_from_file("imports/calibration/cal-ibm-kingston-20260423.json")
# Actually: load multiple files, put in a list
snapshots = [snap1, snap2, snap3]
best = calibration_fetch.resolve_best_snapshot(snapshots, prefer_most_physical=True)
```

Resolution order (first wins):
1. **Highest completeness tier**: `physical` > `metadata` > `absent`
2. **Most populated fields**: sum of non-empty `t1_times`, `t2_times`, `readout_errors`, `gate_errors`, `qubit_freqs`, `readouts`
3. **Newest timestamp**: lexicographic ISO-8601 comparison
4. **First in input list**: stable sort

### Current Corpus Status

- **2 physical**: `cal-ibm-perth-20240402`, `cal-ibm-guadalupe-20240418` — full T1/T2 available
- **2 metadata**: `cal-ibm-kingston-20260423`, `cal-ibm-fez-20260305` — awaiting IBM API data
- **P0 gap**: Obtain physical calibration for `ibm_kingston` and `ibm_fez` from IBM Quantum API

---

## Adding New Artifacts

When adding a new artifact to the corpus:

1. **Determine evidence class** using the decision tree above
2. **Set validation tier** based on how processed the metrics are
3. **Set `backend_generation`** using the generation table
4. **Link calibration** via `calibration_snapshot_id` for non-simulator runs
5. **Create provenance sidecar** with `source_project`, `source_path`, `source_date`, `import_method`
6. **Register claims** in `claims_supported` if the artifact supports specific hypotheses
7. **Run the quality gate** to verify measured-tier readiness:
   ```bash
   python -m gre.research.corpus_report --verbose
   ```
