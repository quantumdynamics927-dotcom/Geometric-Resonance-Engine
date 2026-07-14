# Research Corpus — Import Format

This document describes the import format for bringing external research artifacts
into the GRE research corpus.

## Directory Structure

```
imports/
├── qsg/                          # QSG hardware runs
│   ├── qsg-run-042.json
│   ├── qsg-run-042.provenance.json
│   └── qsg-run-042.summary.md
├── sierpinski/                   # Sierpinski-specific experiments
│   ├── sierpinski-level5-ifs.json
│   ├── sierpinski-level5-ifs.provenance.json
│   └── sierpinski-level5-ifs.summary.md
├── calibration/                  # Calibration snapshots
│   ├── cal-ibm-perth-20240402.json
│   └── cal-ibm-perth-20240402.provenance.json
└── _templates/                   # Reference templates
    ├── hardware_run_template.md
    ├── provenance_sidecar_template.json
    ├── sierpinski_experiment_template.md
    └── calibration_snapshot_template.json
```

## Artifact Types

### Hardware Run (`hardware_run`)

A single execution on quantum hardware or simulator. Stored as JSON or Markdown.

**Required fields:**
- `experiment_id` — Unique identifier (e.g., `qsg-run-042`)
- `project` — Source project name
- `date` — ISO-8601 date string
- `backend` — Backend identifier
- `depth` — Circuit depth
- `shots` — Number of measurement shots
- `qubit_count` — Number of qubits used

**Optional fields:**
- `hypothesis_tag` — Experiment hypothesis (see ExperimentTag enum)
- `circuit_family` — Circuit family used
- `fidelity` — Overall fidelity estimate
- `phi_deviation` — Deviation from 1/φ ≈ 0.618
- `sierpinski_score` — Sierpinski-specific score
- `gate_counts` — Dict of gate type → count
- `notes` — Free-text notes

### Sierpinski Experiment (`sierpinski_experiment`)

A Sierpinski-specific experiment with recursion level, route, and fixed-point data.
Stored as JSON or Markdown.

**Extends Hardware Run fields plus:**
- `recursion_level` — Sierpinski level n (3^n triangles)
- `route` — Mathematical route (`ifs`, `pascal_mod2`, `rule90`, `hanoi`, etc.)
- `depth_invariant_fixed_point` — Observed fixed-point value (expected ≈ 1/φ)
- `depth_invariant_confidence` — Confidence level of fixed-point claim
- `void_encoding_used` — Whether void region was used as decoherence-free subspace
- `fractal_graph_nodes` — Number of nodes in the fractal graph
- `fractal_graph_edges` — Number of edges in the fractal graph
- `hausdorff_dimension` — Expected Hausdorff dimension (log₂(3) ≈ 1.585)

### Calibration Snapshot (`calibration`)

A snapshot of hardware calibration state at a point in time. Stored as JSON.

**Required fields:**
- `snapshot_id` — Unique identifier
- `backend` — Backend name
- `timestamp` — ISO-8601 timestamp

**Optional fields:**
- `t1_times` — T1 relaxation times (dict of qubit → microseconds)
- `t2_times` — T2 dephasing times (dict of qubit → microseconds)
- `readout_errors` — Readout error rates (dict of qubit → probability)
- `gate_errors` — Gate error rates (dict of qubit → probability)
- `qubit_freqs` — Qubit frequencies (dict of qubit → Hz)
- `connectivity` — List of allowed qubit pairs `[[0,1], [1,2], ...]`

## Sidecar Files

Every primary artifact **should** have two sidecar files:

### Provenance Sidecar (`.provenance.json`)

Tracks origin, transformation chain, and sensitivity.

```json
{
  "artifact_id": "sierpinski-level5-ifs",
  "source_project": "sierpinski",
  "source_artifact_id": "sierpinski-level5-ifs",
  "source_path": "sierpinski/results/level5_ifs_2024.json",
  "source_commit": "d9f3b7a",
  "source_date": "2024-02-20",
  "import_date": "2026-07-14",
  "import_method": "json_import",
  "sensitivity": "internal",
  "transform_chain": [
    {
      "step_id": 0,
      "transform_type": "parse",
      "description": "JSON → SierpinskiExperimentRecord",
      "parameters": {}
    }
  ],
  "claims_supported": ["fixed_point_1_over_phi", "sierpinski_depth_invariant"],
  "linked_files": ["sierpinski/sierpinski-level5-ifs.md"],
  "notes": "Level-5 IFS route experiment"
}
```

### Summary Sidecar (`.summary.md`)

Human-readable summary with structured claims and metrics.

```markdown
# Sierpinski Level 5 — IFS Route

**Date**: 2024-02-20
**Backend**: ibmq_qasm_simulator
**Level**: 5
**Fidelity**: 0.891

## Claims
- Depth-invariant fixed point at 1/φ ≈ 0.618 confirmed
- Hausdorff dimension log₂(3) ≈ 1.585 matches ternary channel capacity

## Key Metrics
| Metric | Value |
|--------|-------|
| Fidelity | 0.891 |
| φ deviation | 0.0015 |
| Sierpinski score | 0.904 |
| Depth-invariant fixed point | 0.619 |
| Route | ifs |
```

## Sensitivity Levels

- `open` — Can be shared publicly
- `internal` — Internal use only (default)
- `restricted` — Limited access required
- `confidential` — Highly restricted

## Supported Import Formats

| Format | Record Type | Notes |
|--------|-------------|-------|
| `.json` | HardwareRun, SierpinskiExperiment, Calibration | Standard JSON |
| `.csv` | HardwareRun | First row = headers |
| `.md` | SierpinskiExperiment | YAML frontmatter + body |
| `.provenance.json` | ProvenanceSidecar | Always paired with primary artifact |
| `.summary.md` | ProvenanceSidecar claims | Always paired with primary artifact |

## Normalization

The normalizer module (`gre/research/normalizers.py`) handles:

1. **Field alias resolution** — `experimentId`, `run_id`, `experiment_id` all map to `experiment_id`
2. **Type coercion** — String `"0.891"` → float `0.891`
3. **Default values** — Unknown backend → `"unknown"`, missing hypothesis → `ExperimentTag.OTHER`
4. **Backend name canonicalization** — `ibmq_perth`, `ibm_perth` → `ibmq_perth`
5. **Date normalization** — Multiple date formats → ISO-8601

## Auto-Detection

When `record_kind` is not specified, the normalizer auto-detects type from fields:

- Has `snapshot_id` → `calibration`
- Has `recursion_level` or `route` → `sierpinski_experiment`
- Has `backend` or `fidelity` → `hardware_run`
- Otherwise → `hardware_run` (default)
