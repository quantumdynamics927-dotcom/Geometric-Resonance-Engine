"""Bridge: connect CompilationResult to ResearchCorpus for empirical validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Any, Optional

from .ir import CompilationResult
from .comparison import (
    MatchSummary,
    DivergenceScore,
    CorpusComparisonView as _CCV,
    _get_lambda2,
)


@dataclass
class CorpusComparisonView:
    """Read-only comparison of a CompilationResult against the historical corpus.

    Attributes:
        fidelity_comparison: MatchSummary from node-count based corpus query.
        sierpinski_match: List[SierpinskiExperimentRecord] matching level+route.
        resonance_match: List of corpus records matching the resonance fingerprint.
        attractor_match: List of corpus records matching the attractor signature.
        divergence: DivergenceScore with per-metric deltas from corpus.
        is_measurably_different: True if the result differs from corpus beyond tolerance.
    """
    fidelity_comparison: MatchSummary
    sierpinski_match: List[Any] = field(default_factory=list)
    resonance_match: List[Any] = field(default_factory=list)
    attractor_match: List[Any] = field(default_factory=list)
    divergence: Optional[DivergenceScore] = None
    is_measurably_different: bool = False


def compare_compilation_to_corpus(
    result: CompilationResult,
    corpus: Any,  # ResearchCorpus — avoid import cycle
    tolerance: float = 0.1,
) -> CorpusComparisonView:
    """Bridge CompilationResult → corpus comparison.

    This convenience wrapper:
    1. Extracts graph node count and walk step count from the CompilationResult.
    2. Calls corpus.compare_generated_to_history() for fidelity-based matching.
    3. Finds SierpinskiExperimentRecords at matching level+route.
    4. Computes IQR-based is_measurably_different using spectral_gap vs corpus lambda2.
    5. Returns a structured CorpusComparisonView.

    Args:
        result: CompilationResult from GeometryCompiler.compile().
        corpus: ResearchCorpus instance with historical hardware runs.
        tolerance: Fractional tolerance for node-count matching.

    Returns:
        CorpusComparisonView with fidelity comparison, Sierpinski matches,
        resonance/attractor matches, divergence score, and measurably-different flag.
    """
    # ---- 1. Extract key metrics --------------------------------------------
    graph_nodes = result.graph.adjacency.shape[0]
    primary_walk = next(iter(result.walk_results.values()), None)
    walk_steps = (
        len(primary_walk.walk_result.state_vector_history) - 1
        if primary_walk is not None and primary_walk.walk_result.state_vector_history is not None
        else 0
    )

    # ---- 2. Fidelity-based corpus comparison --------------------------------
    try:
        comparison = corpus.compare_generated_to_history(
            graph_nodes=graph_nodes,
            depth=walk_steps,
            backend="ibmq_qasm_simulator",
            tolerance=tolerance,
        )
    except Exception:
        comparison = {}

    matches = comparison.get("matches", [])
    avg_fidelity = comparison.get("avg_fidelity")
    avg_phi_deviation = comparison.get("avg_phi_deviation")
    avg_sierpinski_score = comparison.get("avg_sierpinski_score")
    best_match = comparison.get("best_match")

    # avg_lambda2 from matches
    lambda2s = [_get_lambda2(m) for m in matches]
    lambda2s = [v for v in lambda2s if v is not None]
    avg_lambda2 = sum(lambda2s) / len(lambda2s) if lambda2s else None

    # best_match_id — handle SierpinskiExperimentRecord (wraps hardware_record)
    best_match_id = None
    if best_match is not None:
        meta = getattr(best_match, "hardware_record", None) or best_match
        best_match_id = getattr(getattr(meta, "metadata", None), "experiment_id", None)

    fidelity_comparison = MatchSummary(
        match_count=len(matches),
        avg_fidelity=avg_fidelity,
        avg_phi_deviation=avg_phi_deviation,
        avg_sierpinski_score=avg_sierpinski_score,
        avg_lambda2=avg_lambda2,
        best_match_id=best_match_id,
        node_tolerance=tolerance,
    )

    # ---- 3. Sierpinski-level matching ---------------------------------------
    # Use recursion level and route from the geometry model
    rec_level = getattr(result.geometry.meta, "level", None)
    route = getattr(result.geometry.meta, "route", None)
    sierpinski_match: List[Any] = []
    if rec_level is not None:
        try:
            sierpinski_match = corpus.find_sierpinski_experiments(
                recursion_level=rec_level,
                route=route,
            )
        except Exception:
            pass

    # avg_lambda2 from Sierpinski matches — route-specific so the reference is precise
    sierp_lambda2s = [_get_lambda2(s) for s in sierpinski_match]
    sierp_lambda2s = [v for v in sierp_lambda2s if v is not None]
    sierp_avg_lam2 = sum(sierp_lambda2s) / len(sierp_lambda2s) if sierp_lambda2s else None

    # ---- 4. Resonance-fingerprint matching ---------------------------------
    resonance_fp = result.resonance_descriptor.to_fingerprint()
    resonance_match: List[Any] = []

    for run in matches:
        run_lam2 = _get_lambda2(run)
        # Build fingerprint proxy: backend:depth:lambda2
        if run_lam2 is not None:
            run_fp = f"{run.backend}:{run.depth}:{round(run_lam2, 6)}"
            if run_fp == resonance_fp:
                resonance_match.append(run)
    # Fallback: accept all fidelity matches as resonance candidates
    if not resonance_match:
        resonance_match = matches[:5]

    # ---- 5. Attractor-signature matching ------------------------------------
    attractor_label = result.attractor_signature.attractor_label
    attractor_match: List[Any] = []
    for run in matches:
        run_label = getattr(run, "attractor_label", None)
        if run_label == attractor_label:
            attractor_match.append(run)
    if not attractor_match:
        attractor_match = matches[:5]

    # ---- 6. Divergence scoring ---------------------------------------------
    import numpy as np

    fidelity_delta = 0.0
    if avg_fidelity is not None and primary_walk is not None:
        gen_fid = getattr(
            primary_walk.walk_result, "state_transfer_fidelity", None
        )
        if gen_fid is not None:
            fidelity_delta = float(abs(gen_fid - avg_fidelity))

    # Prefer Sierpinski-level lambda2 over general fidelity-match average
    lam2_ref = sierp_avg_lam2 if sierp_avg_lam2 is not None else (avg_lambda2 if avg_lambda2 is not None else 0.0)
    spectral_gap_delta = float(
        abs(result.resonance_descriptor.spectral_gap - lam2_ref)
    )
    entropy_delta = float(abs(result.attractor_signature.entropy_rate))
    resonance_delta = float(abs(result.resonance_descriptor.resonance_coupling))

    overall = (
        fidelity_delta + spectral_gap_delta + entropy_delta + resonance_delta
    ) / 4.0

    divergence = DivergenceScore(
        fidelity_delta=fidelity_delta,
        spectral_gap_delta=spectral_gap_delta,
        entropy_delta=entropy_delta,
        resonance_delta=resonance_delta,
        overall=overall,
    )

    # ---- 7. IQR-based measurably different ---------------------------------
    is_measurably_different = False
    try:
        all_lambda2s: List[float] = []

        # From hardware_runs
        for run in corpus.hardware_runs.values():
            v = _get_lambda2(run)
            if v is not None:
                all_lambda2s.append(v)

        # From sierpinski_experiments
        for rec in corpus.sierpinski_experiments.values():
            v = _get_lambda2(rec)
            if v is not None:
                all_lambda2s.append(v)

        if len(all_lambda2s) >= 3:
            q1 = float(np.percentile(all_lambda2s, 25))
            q3 = float(np.percentile(all_lambda2s, 75))
            iqr = q3 - q1
            median = float(np.median(all_lambda2s))
            sg = result.resonance_descriptor.spectral_gap
            if iqr == 0:
                deviation = abs(sg - median) / (abs(median) + 1e-12)
            else:
                deviation = abs(sg - median) / iqr
            is_measurably_different = deviation > 1.5
        else:
            is_measurably_different = True  # Insufficient reference
    except Exception:
        is_measurably_different = True

    return CorpusComparisonView(
        fidelity_comparison=fidelity_comparison,
        sierpinski_match=sierpinski_match,
        resonance_match=resonance_match,
        attractor_match=attractor_match,
        divergence=divergence,
        is_measurably_different=is_measurably_different,
    )
