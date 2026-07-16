"""Read-only corpus comparison view — wires CompilationResult into the ResearchCorpus."""

from __future__ import annotations

from .ir import CompilationResult
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import numpy as np


def _get_lambda2(run: Any) -> Optional[float]:
    """Extract lambda2 (spectral gap) from a corpus record.

    HardwareRunRecord stores it in observed_metrics.get("lambda2").
    SierpinskiExperimentRecord wraps a hardware_record with the same field.
    """
    # SierpinskiExperimentRecord has .hardware_record
    hw = getattr(run, "hardware_record", None)
    if hw is not None:
        obs = getattr(hw, "observed_metrics", None)
    else:
        obs = getattr(run, "observed_metrics", None)
    if obs:
        return obs.get("lambda2")
    return None


def _get_sierpinski_record(run: Any) -> Optional[Any]:
    """Return SierpinskiExperimentRecord if the run is one, else None."""
    from ..research.schemas import SierpinskiExperimentRecord
    if isinstance(run, SierpinskiExperimentRecord):
        return run
    return None


@dataclass
class MatchSummary:
    match_count: int
    avg_fidelity: Optional[float]
    avg_phi_deviation: Optional[float]
    avg_sierpinski_score: Optional[float]
    avg_lambda2: Optional[float]
    best_match_id: Optional[str]
    node_tolerance: float


@dataclass
class DivergenceScore:
    fidelity_delta: float
    spectral_gap_delta: float
    entropy_delta: float
    resonance_delta: float
    overall: float


class CorpusComparisonView:
    """Read-only comparison of a CompilationResult against the historical corpus.

    Query methods:
        by_fidelity(): MatchSummary based on qubit_count ≈ graph node count.
        by_sierpinski(level, route): List[SierpinskiExperimentRecord] for same level+route.
        is_measurably_different(): bool — IQR outlier test on lambda2.
        divergence_score(): DivergenceScore — per-metric Δ from corpus means.
    """

    def __init__(
        self,
        result: CompilationResult,
        corpus: Any,  # ResearchCorpus — avoid import cycle
        tolerance: float = 0.1,
    ):
        self.result = result
        self.corpus = corpus
        self.tolerance = tolerance

    # --------------------------------------------------------------------------
    # Helpers
    # --------------------------------------------------------------------------

    def _graph_nodes(self) -> int:
        return self.result.graph.adjacency.shape[0]

    def _walk_steps(self) -> int:
        primary = next(iter(self.result.walk_results.values()), None)
        if primary is None:
            return 0
        hist = primary.walk_result.state_vector_history
        return max(0, len(hist) - 1) if hist is not None else 0

    def _all_lambda2s(self) -> List[float]:
        """Collect all lambda2 values from hardware_runs + sierpinski_experiments."""
        values: List[float] = []

        # From hardware_runs dict
        for run in self.corpus.hardware_runs.values():
            v = _get_lambda2(run)
            if v is not None:
                values.append(v)

        # From sierpinski_experiments dict
        for rec in self.corpus.sierpinski_experiments.values():
            v = _get_lambda2(rec)
            if v is not None:
                values.append(v)

        return values

    def _sierpinski_matches(
        self,
        level: Optional[int] = None,
        route: Optional[str] = None,
    ) -> List[Any]:
        """Find SierpinskiExperimentRecords matching level/route."""
        return self.corpus.find_sierpinski_experiments(
            recursion_level=level,
            route=route,
        )

    # --------------------------------------------------------------------------
    # Query API
    # --------------------------------------------------------------------------

    def by_fidelity(
        self,
        backend: str = "ibmq_qasm_simulator",
    ) -> MatchSummary:
        """Match by qubit_count ≈ graph node count, depth ≈ walk_steps."""
        n = self._graph_nodes()
        depth = self._walk_steps()

        try:
            comparison = self.corpus.compare_generated_to_history(
                graph_nodes=n,
                depth=depth,
                backend=backend,
                tolerance=self.tolerance,
            )
        except Exception:
            comparison = {}

        matches = comparison.get("matches", [])
        avg_fid = comparison.get("avg_fidelity")
        avg_phi = comparison.get("avg_phi_deviation")
        avg_ss = comparison.get("avg_sierpinski_score")
        best = comparison.get("best_match")

        # Compute avg_lambda2 from matches
        lambda2s = [_get_lambda2(m) for m in matches]
        lambda2s = [v for v in lambda2s if v is not None]
        avg_lam2 = sum(lambda2s) / len(lambda2s) if lambda2s else None

        # best_match_id — handle SierpinskiExperimentRecord (wraps hardware_record)
        best_match_id = None
        if best is not None:
            meta = getattr(best, "hardware_record", None) or best
            best_match_id = getattr(getattr(meta, "metadata", None), "experiment_id", None)

        return MatchSummary(
            match_count=len(matches),
            avg_fidelity=avg_fid,
            avg_phi_deviation=avg_phi,
            avg_sierpinski_score=avg_ss,
            avg_lambda2=avg_lam2,
            best_match_id=best_match_id,
            node_tolerance=self.tolerance,
        )

    def by_sierpinski(
        self,
        level: Optional[int] = None,
        route: Optional[str] = None,
    ) -> List[Any]:
        """Find corpus Sierpinski experiments at matching level+route."""
        return self._sierpinski_matches(level=level, route=route)

    def is_measurably_different(
        self,
        threshold: float = 1.5,
        metric: str = "spectral_gap",
    ) -> bool:
        """IQR-based outlier test: return True if result deviates from corpus.

        Uses spectral_gap (compiler λ₂) vs corpus lambda2 (hardware λ₂).
        deviation > threshold (default 1.5× IQR) → measurably different.
        """
        if metric == "spectral_gap":
            value = self.result.resonance_descriptor.spectral_gap
        elif metric == "entropy_rate":
            value = self.result.attractor_signature.entropy_rate
        elif metric == "golden_ratio_ratio":
            value = self.result.resonance_descriptor.golden_ratio_ratio
        else:
            return False

        corpus_values = self._all_lambda2s()
        if len(corpus_values) < 3:
            return True  # No sufficient reference → assume different

        q1 = float(np.percentile(corpus_values, 25))
        q3 = float(np.percentile(corpus_values, 75))
        iqr = q3 - q1
        median = float(np.median(corpus_values))

        if iqr == 0:
            deviation = abs(value - median) / (abs(median) + 1e-12)
        else:
            deviation = abs(value - median) / iqr

        return deviation > threshold

    def divergence_score(self) -> DivergenceScore:
        """Per-metric divergence from corpus means."""
        corpus_values = self._all_lambda2s()
        avg_lambda2 = float(np.mean(corpus_values)) if corpus_values else 0.0

        # Fidelity delta
        fid_summary = self.by_fidelity()
        fidelity_delta = 0.0
        if fid_summary.avg_fidelity is not None:
            primary = next(iter(self.result.walk_results.values()), None)
            gen_fid = (
                primary.walk_result.state_transfer_fidelity
                if primary and hasattr(primary.walk_result, "state_transfer_fidelity")
                else None
            )
            if gen_fid is not None:
                fidelity_delta = float(abs(gen_fid - fid_summary.avg_fidelity))

        spectral_gap_delta = float(
            abs(self.result.resonance_descriptor.spectral_gap - avg_lambda2)
        )
        entropy_delta = float(abs(self.result.attractor_signature.entropy_rate))
        resonance_delta = float(abs(self.result.resonance_descriptor.resonance_coupling))

        overall = (
            fidelity_delta + spectral_gap_delta + entropy_delta + resonance_delta
        ) / 4.0

        return DivergenceScore(
            fidelity_delta=fidelity_delta,
            spectral_gap_delta=spectral_gap_delta,
            entropy_delta=entropy_delta,
            resonance_delta=resonance_delta,
            overall=overall,
        )
