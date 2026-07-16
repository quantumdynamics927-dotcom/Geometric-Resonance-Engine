# Hardware Run Plan — Manual IBM Quantum Submission

## Overview

Staged circuits for manual submission to `ibm_kingston` and `ibm_fez`. Do NOT auto-submit — review `staged/hardware_run_plan/` before running any `ibm quantum job submit` commands.

After hardware execution:
1. Copy results into `staged/hardware_run_plan/` manually
2. Add `staged_hardware` to `SOURCES` in `scripts/import_new_ibm_jobs.py`
3. Run `python scripts/import_new_ibm_jobs.py --source staged_hardware`
4. Run `python scripts/compute_lambda2_from_counts.py` to backfill λ₂
5. Re-run corpus bridge comparison

## Circuit Inventory

| Route | Level | Backend | Qubits | Depth | QASM File | Shot Count |
|---|---|---|---|---|---|---|
| hanoi | 4 | ibm_kingston | 128 | 11 | `hanoi-L4-ibm_kingston.qasm` | 8192 |
| hanoi | 4 | ibm_fez | 128 | 11 | `hanoi-L4-ibm_fez.qasm` | 8192 |
| hanoi | 5 | ibm_kingston | 256 | 11 | `hanoi-L5-ibm_kingston.qasm` | 8192 |
| hanoi | 5 | ibm_fez | 256 | 11 | `hanoi-L5-ibm_fez.qasm` | 8192 |
| pascal_mod2 | 4 | ibm_kingston | 128 | 11 | `pascal_mod2-L4-ibm_kingston.qasm` | 8192 |
| pascal_mod2 | 4 | ibm_fez | 128 | 11 | `pascal_mod2-L4-ibm_fez.qasm` | 8192 |
| pascal_mod2 | 5 | ibm_kingston | 256 | 11 | `pascal_mod2-L5-ibm_kingston.qasm` | 8192 |
| pascal_mod2 | 5 | ibm_fez | 256 | 11 | `pascal_mod2-L5-ibm_fez.qasm` | 8192 |
| rule90 | 4 | ibm_kingston | 32 | 11 | `rule90-L4-ibm_kingston.qasm` | 8192 |
| rule90 | 4 | ibm_fez | 32 | 11 | `rule90-L4-ibm_fez.qasm` | 8192 |
| rule90 | 5 | ibm_kingston | 64 | 11 | `rule90-L5-ibm_kingston.qasm` | 8192 |
| rule90 | 5 | ibm_fez | 64 | 11 | `rule90-L5-ibm_fez.qasm` | 8192 |

## Compiler Metadata (Expected Values)

| Route | Level | Graph Nodes | Graph Edges | Avg Degree | λ₂ (spectral gap) | λ₂/λ₃ spacing | Attractor Label |
|---|---|---|---|---|---|---|---|
| hanoi | 4 | 81 | ~195 | ~4.82 | **0.435** (outlier) | — | TBD |
| hanoi | 5 | 243 | — | — | — | — | TBD |
| pascal_mod2 | 4 | 83 | — | — | — | — | TBD |
| pascal_mod2 | 5 | 251 | — | — | — | — | TBD |
| rule90 | 4 | 81 | — | — | — | — | TBD |
| rule90 | 5 | 241 | — | — | — | — | TBD |

> **Note:** λ₂ and attractor values are compiler-predicted from the contraction-index graph. Hardware results will populate the "TBD" cells. The hanoi L4 λ₂=0.435 is a structural outlier (>12× corpus median) — flag in any analysis writeup.

## Submission Commands

Submit one job at a time via IBM Quantum CLI:

```bash
# Example — hanoi L4 on ibm_kingston
ibm quantum job submit \
  --backend ibm_kingston \
  --shots 8192 \
  --file staged/hardware_run_plan/hanoi-L4-ibm_kingston.qasm \
  --tag route:hanoi \
  --tag level:4 \
  --tag hypothesis:sierpinski_depth_invariant \
  --tag circuit_family:fractal_walk

# Example — pascal_mod2 L4 on ibm_kingston
ibm quantum job submit \
  --backend ibm_kingston \
  --shots 8192 \
  --file staged/hardware_run_plan/pascal_mod2-L4-ibm_kingston.qasm \
  --tag route:pascal_mod2 \
  --tag level:4 \
  --tag hypothesis:sierpinski_depth_invariant \
  --tag circuit_family:fractal_walk

# Example — rule90 L4 on ibm_kingston
ibm quantum job submit \
  --backend ibm_kingston \
  --shots 8192 \
  --file staged/hardware_run_plan/rule90-L4-ibm_kingston.qasm \
  --tag route:rule90 \
  --tag level:4 \
  --tag hypothesis:sierpinski_depth_invariant \
  --tag circuit_family:fractal_walk
```

Repeat for `ibm_fez` backend using the corresponding `.qasm` files.

## Calibration Snapshots

| Backend | Calibration Snapshot ID |
|---|---|
| ibm_kingston | `cal-ibm-kingston-20260423` |
| ibm_fez | `cal-ibm-fez-20260305` |

Record the actual calibration snapshot ID from the job result's provenance after execution — these stubs are approximations based on last-known dates.

## Hypothesis

`sierpinski_depth_invariant`: The spectral gap (λ₂) and attractor signature of a fractal quantum walk are determined by the underlying graph topology (route), not the recursion depth (level). At same route, level 4 and level 5 circuits should produce statistically indistinguishable λ₂ and attractor outcomes. Different routes (hanoi, pascal_mod2, rule90) at the same level should produce measurably different signatures.

This is the "depth invariance" hypothesis — a test of whether the compiler's graph abstraction captures the physically relevant structure across recursion depths.
