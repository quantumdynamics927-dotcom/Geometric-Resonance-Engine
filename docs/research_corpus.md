# Research Corpus

The GRE research corpus provides a structured, queryable archive of prior experimental results from QSG, Sierpinski, calibration, and other prior projects — imported into GRE as canonical evidence records.

## Overview

The corpus lives in the `imports/` directory at the repo root. Each artifact is stored in its original format (JSON, Markdown, CSV) alongside provenance sidecars that track origin, transformation, and sensitivity.

```
imports/
├── qsg/                   # QSG hardware runs
├── sierpinski/            # Sierpinski-specific experiments
├── calibration/          # Calibration snapshots
└── _templates/           # Reference templates
```

## Loading the Corpus

```python
from gre.research import load_corpus, list_projects, query_runs

# Load all imported artifacts
corpus, catalog, stats = load_corpus()

# List available projects
print(list_projects(corpus))
# → ['qsg', 'sierpinski', 'calibration']

# Query hardware runs
runs = query_runs(depth=5, backend="ibmq_qasm_simulator")
```

## Query Functions

### `query_runs(...)`

Query hardware runs with filtered parameters:

```python
from gre.research import query_runs
from gre.research.schemas import ExperimentTag

# Filter by multiple criteria
runs = query_runs(
    depth=5,
    backend="ibmq_qasm_simulator",
    project="sierpinski",
    hypothesis_tag=ExperimentTag.FIXED_POINT_1_OVER_PHI,
    min_fidelity=0.85,
)
```

### `query_sierpinski(...)`

Query Sierpinski-specific experiments:

```python
from gre.research import query_sierpinski

# All IFS-route experiments at level 4+
experiments = query_sierpinski(route="ifs", min_level=4)

# Check fixed-point consistency
for exp in experiments:
    if exp.depth_invariant_fixed_point is not None:
        print(f"{exp.experiment_id}: {exp.depth_invariant_fixed_point:.4f}")
```

### `compare_to_generated(...)`

Compare a newly generated GRE structure against the historical corpus:

```python
from gre.research import compare_to_generated

comparison = compare_to_generated(
    corpus=corpus,
    graph_nodes=33,
    depth=3,
    backend="ibmq_qasm_simulator",
    fidelity=0.891,
    phi_deviation=0.0015,
)

print(f"Best match: {comparison.best_match_similarity:.3f}")
print(f"Matching records: {len(comparison.matching_records)}")
print(f"Evidence for claims: {comparison.claim_supported}")
print(f"Linkage strength: {comparison.linkage_strength:.2f}")
```

### `get_claim(claim_id)` and `evidence_chain(claim_id)`

Retrieve claims and trace their supporting evidence:

```python
from gre.research import get_claim, evidence_chain

# Get a claim by ID
claim = get_claim("fixed_point_1_over_phi")
print(f"Confidence: {claim.confidence:.2f}")
print(f"Artifacts: {claim.source_artifacts}")

# Build the full evidence chain
chain = evidence_chain("fixed_point_1_over_phi")
print(f"Supporting artifacts: {len(chain['supporting_artifacts'])}")
print(f"Calibration context: {len(chain['calibration_context'])}")
```

## Record Types

### HardwareRunRecord

Normalized record of a hardware or simulator execution. Contains:
- `metadata` (experiment_id, project, date, hypothesis_tag, circuit_family, notes)
- `backend`, `qubit_count`, `depth`, `shots`
- `fidelity`, `phi_deviation`, `sierpinski_score`
- `observed_metrics` (arbitrary key-value pairs)
- `provenance` (source project, path, commit, transform chain)

### SierpinskiExperimentRecord

Extends HardwareRunRecord with Sierpinski-specific fields:
- `recursion_level` (3^n triangles)
- `hausdorff_dimension` (log₂(3) ≈ 1.585)
- `depth_invariant_fixed_point` (expected ≈ 1/φ ≈ 0.618)
- `depth_invariant_confidence`
- `route` (ifs, pascal_mod2, rule90, hanoi, etc.)
- `void_encoding_used`
- `fractal_graph_nodes`, `fractal_graph_edges`

### CalibrationSnapshot

Hardware calibration state snapshot:
- `snapshot_id`, `backend`, `timestamp`
- `t1_times`, `t2_times` (relaxation/dephasing times)
- `readout_errors`, `gate_errors`
- `qubit_freqs`, `connectivity`

## Corpus Statistics

```python
corpus, catalog, stats = load_corpus()

print(f"Total artifacts: {stats.total_entries}")
print(f"  Hardware runs: {stats.hardware_runs_loaded}")
print(f"  Sierpinski experiments: {stats.sierpinski_experiments_loaded}")
print(f"  Calibration snapshots: {stats.calibrations_loaded}")
print(f"  Skipped: {stats.skipped}")
print(f"  Errors: {stats.errors}")

# Catalog stats
print(f"Projects: {catalog.projects()}")
print(f"By backend: {catalog.stats()['by_backend']}")
```

## Catalog API

```python
from gre.research.catalog import discover_imports_dir

catalog = discover_imports_dir(Path("imports"))

# All projects
print(catalog.projects())

# Entries for a specific project
for entry in catalog.by_project("sierpinski"):
    print(f"  {entry.artifact_id} ({entry.backend})")

# Search with filters
entries = catalog.search(
    artifact_type="sierpinski_experiment",
    min_depth=4,
)
```

## Normalization

All source formats are normalized to canonical record types:

- Field aliases resolved (`experimentId` → `experiment_id`)
- Type coercion applied (string → float/int as appropriate)
- Default values for missing fields
- Backend name canonicalization
- Date normalization to ISO-8601

See [import_format.md](import_format.md) for full format documentation.

## Claims and Evidence

Claims are stored as `ImportedClaimRecord` objects linked to the artifacts that support them:

```python
from gre.research.linkage import ClaimLinkage, ImportedClaimRecord
from gre.research.schemas import ExperimentTag

linkage = ClaimLinkage()
claim = ImportedClaimRecord(
    claim_id="my_claim",
    claim_type=ExperimentTag.FIXED_POINT_1_OVER_PHI,
    description="1/φ fixed point observed",
    hypothesis="Fixed point emerges from recursive structure",
    evidence=["run-001", "run-002"],
    source_artifacts=["artifact-001"],
    confidence=0.93,
)
linkage.register_claim(claim)
```
