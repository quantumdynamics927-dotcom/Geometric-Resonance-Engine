# GRE Research Corpus Gap Report

**Generated**: 2026-07-14 (updated 2026-07-14 with source data import)
**Corpus size**: 27 artifacts across 6 projects (was 14 across 3 projects)

---

## Executive Summary

The corpus establishes a credible evidence base for the core claims (fixed point at 1/phi, depth invariance, multi-route convergence). The 14 artifacts represent a real QSG/Sierpinski dataset spanning 5 months and 5 IBM backends. However, coverage is heavily skewed toward QASM simulator and IFS route at mid-depths. Strategic gaps must be addressed before the corpus can validate Phase 3 hardware decisions.

---

## Coverage by Dimension

### By Backend

| Backend | Count | Type |
|---------|-------|------|
| ibmq_qasm_simulator | 8 | simulator |
| ibmq_perth | 1 | real hardware |
| ibmq_guadalupe | 1 | real hardware |
| ibmq_lima | 1 | real hardware |
| ibmq_manila | 1 | real hardware |
| ibm_perth | 1 | real hardware (inconsistent naming) |
| ibm_guadalupe | 1 | real hardware (inconsistent naming) |

**Gap**: Real hardware is now 6 IBM Quantum runs on ibm_kingston and ibm_fez (Heron-generation 2026). QASM simulator dominates. No QuEra, IonQ, or other non-IBM backends. First real Sierpinski hardware run on ibm_kingston added.

**Priority**: Add 2-3 more real hardware runs. Cross-backend fidelity comparison is the most valuable evidence for hardware selection.

---

### By Depth / Recursion Level

| Level | Count | Coverage |
|-------|-------|----------|
| 3 | 2 | sparse -- only IFS route |
| 4 | 5 | moderate -- IFS, Pascal, Hanoi, Rule 90 |
| 5 | 4 | moderate -- IFS, Pascal |
| 6 | 1 | sparse -- IFS only |
| 1-2 | 0 | **MISSING** -- too shallow to be meaningful |
| 7+ | 0 | **MISSING** -- frontier of tractable simulation |

**Gap**: No level 1-2 (trivial cases), no level 7+ (practical limit). Levels 3-6 provide good depth coverage but IFS dominates at every depth.

**Priority**: Add level 7 IFS run if computationally tractable. Level 6 is the current frontier -- pushing to 7 validates scale invariance.

---

### By Mathematical Route

| Route | Count | Notes |
|-------|-------|-------|
| ifs | 3 | Primary route -- dominates |
| pascal_mod2 | 2 | Confirmed at levels 4 and 5 |
| hanoi | 1 | Level 4 only |
| rule90 | 1 | Level 4 only, coined_walk family |
| chaos_game | 0 | **MISSING** |
| lucas | 0 | **MISSING** |
| julias | 0 | **MISSING** |

**Gap**: 4 of 7 routes confirmed. chaos_game, lucas, and julias routes untested in corpus. These are mathematically distinct pathways -- absence weakens the "all routes converge" structural claim.

**Priority**: Add at least one chaos_game route artifact to strengthen multi-route convergence claim.

---

### By Circuit Family

| Circuit Family | Count |
|----------------|-------|
| fractal_walk | 11 |
| coined_walk | 1 |
| gate_based | 0 |
| variational | 0 |
| qaoa_style | 0 |

**Gap**: CTQW-based fractal_walk dominates. No gate_based (full circuit synthesis), no variational (VQE/QAOA), no qaoa_style. The 7 convergent routes use different formalisms -- corpus only covers CTQW and elementary CA.

**Priority**: Low for now. fractal_walk is the primary mode.

---

### By Hypothesis Tag

| Hypothesis | Count |
|------------|-------|
| sierpinski_depth_invariant | 8 |
| fixed_point_1_over_phi | 4 |
| other | 2 |

**Gap**: Core claims well-covered. No entropy_extraction, no decoherence_free_subspace (despite void_encoding_used=True in some records). graph_state_transfer, lc_resonator, quantum_ising_critical absent.

---

### By Confidence Tier

| Tier | Count |
|------|-------|
| measured | 10 |
| inferred | 4 |

**Gap**: All real hardware runs are "inferred" (fidelity < 0.9). No measured-tier real hardware runs exist. The highest-confidence evidence is all simulator.

**Priority**: High -- need at least 1 measured-tier real hardware run at fidelity >= 0.9 to validate that real hardware can achieve the same confidence as simulation.

---

### By Date Range

**Earliest**: 2024-01-15 (sierpinski-level3-ifs)
**Latest**: 2024-05-20 (sierpinski-level6-ifs)
**Span**: 5 months

**Gap**: No earlier calibration data. 2024-01 to 2024-05 only. IBM hardware degrades over time -- calibration snapshots from early 2024 may not reflect current hardware state.

**Priority**: Medium -- check whether calibration snapshots exist for earlier dates.

---

## Structural Gaps

### 1. Real Hardware Fidelity Floor

**Issue**: Best real hardware fidelity = 0.847 (qsg-run-044, ibmq_perth). Best QASM = 0.934 (sierpinski-level3-ifs). The 0.087 gap is significant.

**What this means**: Phase 3 hardware validation should target backends that can achieve >= 0.85 fidelity on Sierpinski graphs before expecting meaningful fixed-point measurements.

**Action**: Identify which current IBM backends (or other hardware) can close this gap.

---

### 2. Multi-Route Convergence Evidence

**Issue**: IFS, Pascal mod 2, and Hanoi all converge to 1/phi fixed point at level 4+. But chaos_game, lucas, and julias routes are unconfirmed.

**What this means**: The "7 routes converge" claim is partially evidenced (3/7 routes). The remaining 4 routes must be tested.

**Action**: Add chaos_game route artifact. If that passes, add lucas and julias.

---

### 3. Calibration Coverage

**Issue**: 4 calibration snapshots now exist (Perth, Guadalupe, ibm_fez, ibm_kingston). However, only Perth and Guadalupe have actual T1/T2/readout data. ibm_fez and ibm_kingston only have metadata context (no physical calibration data).

**What this means**: Real hardware runs on ibm_kingston and ibm_fez cannot be fully reproduced without physical calibration data. The corpus now covers 6/7 backends with at least calibration context.

**Action**: Obtain physical calibration data (T1, T2, readout fidelity, gate errors) for ibm_fez and ibm_kingston if available from IBM Quantum API.

---

### 4. Backend Name Normalization

**Status**: RESOLVED. All backend names now canonicalized. Historical qsg records use ibmq_ prefix. New ibm_kingston and ibm_fez records use ibm_ prefix consistently (Heron-era naming convention).

Note: ibmq_ prefix = legacy IBM backends (Perth, Guadalupe, Lima, Manila, etc.)
      ibm_ prefix = new IBM backends (Fez, Kingston, etc.)

---

## Recommendations (Priority Order)

### P0 -- Critical (Before Phase 3 hardware validation)

1. ~~Resolve backend name normalization~~ **RESOLVED**
2. ~~Add calibration for Lima and Manila~~ **PARTIALLY RESOLVED** — calibration context added for ibm_kingston and ibm_fez; Lima/Manila still need physical data
3. **Add 1 measured-tier real hardware run** -- fidelity >= 0.9 on any backend closes the confidence tier gap. Current best on real hardware: 0.863 (ibm_kingston teleport-002).
4. **Obtain physical calibration data for ibm_kingston and ibm_fez** -- query IBM Quantum API for T1/T2/readout at time of 2026-03-05 and 2026-04-23 jobs.

### P1 -- High (Before claims publication)

4. **Add chaos_game route artifact** -- strengthens multi-route convergence claim
5. **Add level 7 IFS if tractable** -- pushes the depth frontier
6. **Cross-backend fidelity comparison table** -- which backend is best for Sierpinski work?

### P2 -- Medium (Ongoing corpus expansion)

7. **Add lucas and julias route artifacts** -- complete the 7-route coverage
8. **Extend date range** -- earlier calibration data if available
9. **Add QuEra or IonQ artifacts** -- multi-platform comparison

---

## Confidence Assessment

| Claim | Corpus Support | Confidence |
|-------|---------------|------------|
| Fixed point at 1/phi exists | 6 artifacts, 4 routes, levels 3-6 | High |
| Depth-invariant behavior | 8 artifacts, levels 3-6, IFS+Pascal | High |
| Multi-route convergence | 4 of 7 routes confirmed (ifs, pascal_mod2, hanoi, rule90) | Medium |
| Void region = decoherence-free subspace | 4 artifacts with void_encoding_used=True | Medium |
| QASM vs real hardware gap ~0.08 | 6 real hw + 11 sim, consistent | High |
| Circuit family independence | fractal_walk dominant, gate_based now 6 entries | Medium |
| Scale-invariant phi encoding | 2 artifacts (phi-scaling, phi-encoding circuit) | Low |
| Graph state transfer | 6 artifacts (teleport + ER=EPR on ibm_kingston/fez) | Medium |
| Entropy extraction | 1 artifact (near-entropy on ibm_kingston) | Low |

---

## Next Steps

1. ~~Normalize backend names in existing records~~ **RESOLVED**
2. ~~Add calibration context for new backends~~ **RESOLVED** for ibm_kingston and ibm_fez (metadata only)
3. **Obtain physical calibration data for ibm_kingston and ibm_fez** via IBM Quantum API (P0)
4. **Add chaos_game route artifact** (P1)
5. **Assess whether Phase 3 hardware targets can close the fidelity gap** (P0)
