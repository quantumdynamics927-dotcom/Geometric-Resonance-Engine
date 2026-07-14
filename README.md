# Geometric Resonance Engine

**GRE** — a Python library and research corpus for fractal-graph quantum information architecture, built around the Sierpinski triangle as a canonical information geometry.

## What This Is

The Geometric Resonance Engine investigates how fractal geometry — specifically the Sierpinski triangle — structures quantum information flow. It models quantum walks on fractal graphs, compares against IBM Quantum hardware execution results, and maintains a curated corpus of prior experimental data.

### Core Research Questions
- Does the Sierpinski graph produce a depth-invariant fixed point at 1/φ ≈ 0.618?
- Can fractal geometry serve as a decoherence-free subspace architecture?
- Which of 7 independent mathematical routes to the Sierpinski triangle converges experimentally?

## Architecture

```
gre/
├── core/          Data models: Node, Edge, GraphModel, CircuitModel
├── fractals/      Generators: SierpinskiGenerator (7 routes), FractalRegistry
├── simulation/    Classical baselines: QuantumWalkSimulator, entropy metrics
├── quantum/       Circuit mapping: GraphCircuitMapper, QuantumWalkCircuitBuilder
└── research/      Corpus: HardwareRunRecord, SierpinskiExperimentRecord,
                   CalibrationSnapshot, provenance chain, query API
```

## Installation

```bash
pip install -e .
```

Requirements: Python 3.10+, Qiskit 1.x, NumPy, SciPy, Pydantic 2.x

## Research Corpus

The corpus (`imports/`) contains 48 artifacts across 6 projects:

- **IBM Quantum hardware runs** on ibm_herron (kingston, fez), ibm_eagle, ibm_falcon, and simulators
- **Sierpinski experiments** at recursion levels 3–6 across 5 routes (IFS, Pascal, Rule 90, Hanoi, chaos game)
- **Calibration snapshots** with physical T1/T2 data for ibmq_perth and ibmq_guadalupe
- **Phi-encoding circuits** (merkaba, tmt projects)

Query the corpus:

```python
from gre.research import load_corpus, query_runs

corpus, catalog, stats = load_corpus()

# Find all ibm_kingston runs
runs = query_runs(backend="ibm_kingston")
for r in runs:
    print(f"{r.metadata.experiment_id}: fidelity={r.fidelity}")

# Compare new result against historical runs
from gre.research import compare_to_generated
comparison = compare_to_generated(graph_nodes=33, depth=3, backend="ibmq_qasm_simulator")
```

See `docs/corpus_taxonomy.md` for evidence classification (historical_real / synthetic_seed / derived_summary) and validation tier definitions.

## Running Tests

```bash
pytest tests/ -v
```

Current: 68 tests passing.

## Key Design Decisions

- **Continuous-time CTQW** via normalized Laplacian exponential — always unitary, no staggering collapse
- **Dyadic rational vertex deduplication** — scale = 2^level prevents hash collisions
- **1/φ fixed point** — should emerge from state transfer fidelity vs step scans
- **Evidence taxonomy** — historical_real vs synthetic_seed vs derived_summary, with validation tiers raw → normalized → benchmarked → measured
