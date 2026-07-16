from ..simulation.quantum_walk import WalkResult
from ..core.graph import GraphModel
from .ir import AttractorSignature
from typing import Tuple, Optional
import numpy as np


class AttractorSignatureClassifier:
    """Classify quantum walk behavior into named attractor signatures.

    Three orthogonal axes:
    1. entropy_trajectory: how does Shannon entropy of the state evolve?
    2. participation_ratio_trend: is the walk localizing or delocalizing?
    3. transfer_class: how well does state transfer from source to target?
    """

    def classify(self, walk_result: WalkResult, graph: GraphModel) -> AttractorSignature:
        entropy_trajectory, entropy_rate = self._classify_entropy(walk_result)
        pr_final = float(walk_result.participation_ratio) if walk_result.participation_ratio is not None else 0.0
        pr_trend = self._classify_pr_trend(walk_result)
        transfer_class, optimal_steps = self._classify_transfer(walk_result, graph)
        eigenstate_correlation = self._eigenstate_correlation(walk_result, graph)

        attractor_label = f"{entropy_trajectory}_{pr_trend}_{transfer_class}"

        return AttractorSignature(
            entropy_trajectory=entropy_trajectory,
            entropy_rate=entropy_rate,
            participation_ratio_final=pr_final,
            participation_ratio_trend=pr_trend,
            transfer_class=transfer_class,
            optimal_transfer_steps=optimal_steps,
            eigenstate_correlation=eigenstate_correlation,
            attractor_label=attractor_label,
        )

    def _shannon_entropy(self, probs: np.ndarray) -> float:
        """Shannon entropy H = -sum(p * log(p))."""
        p = probs[probs > 0]
        return float(-np.sum(p * np.log2(p)))

    def _classify_entropy(self, walk_result: WalkResult) -> Tuple[str, float]:
        """Classify entropy trajectory over state_vector_history.

        Classification:
        - stable: H_final ≈ H_initial ± 5%
        - increasing: H grows monotonically or >10% total growth
        - decreasing: H drops monotonically or >10% total drop
        - oscillating: >2 direction reversals with amplitude >5%
        """
        history = walk_result.state_vector_history
        if history is None or len(history) < 2:
            return "stable", 0.0

        entropies = []
        for state in history:
            probs = np.abs(state) ** 2
            probs = probs / (np.sum(probs) + 1e-12)
            entropies.append(self._shannon_entropy(probs))

        H_initial = entropies[0]
        H_final = entropies[-1]
        H_range = max(entropies) - min(entropies)

        if H_initial == 0:
            return "stable", 0.0

        pct_change = (H_final - H_initial) / H_initial
        H_threshold = 0.05  # 5% tolerance for "stable"

        # Count direction reversals
        reversals = 0
        for i in range(1, len(entropies) - 1):
            delta_prev = entropies[i] - entropies[i - 1]
            delta_next = entropies[i + 1] - entropies[i]
            if delta_prev * delta_next < 0:
                reversals += 1

        if reversals >= 2 and H_range > H_threshold * H_initial:
            return "oscillating", float(entropies[-1] - entropies[0]) / len(entropies)
        elif pct_change > 0.10:
            return "increasing", float(pct_change)
        elif pct_change < -0.10:
            return "decreasing", float(pct_change)
        else:
            return "stable", float(pct_change)

    def _classify_pr_trend(self, walk_result: WalkResult) -> str:
        """Classify participation ratio trend.

        - localizing: PR decreases (wave localizes)
        - delocalizing: PR increases (wave spreads)
        - stable: PR changes <10%
        - oscillating: PR oscillates with >2 reversals
        """
        history = walk_result.state_vector_history
        if history is None or len(history) < 2:
            return "stable"

        pr_traj = []
        for state in history:
            probs = np.abs(state) ** 2
            pr = 1.0 / (np.sum(probs ** 2) + 1e-12)  # Inverse participation ratio
            pr_traj.append(pr)

        pr_initial = pr_traj[0]
        pr_final = pr_traj[-1]

        if pr_initial == 0:
            return "stable"

        pct_change = (pr_final - pr_initial) / pr_initial

        # Count reversals
        reversals = 0
        for i in range(1, len(pr_traj) - 1):
            if (pr_traj[i] - pr_traj[i - 1]) * (pr_traj[i + 1] - pr_traj[i]) < 0:
                reversals += 1

        if reversals >= 2 and max(pr_traj) / (min(pr_traj) + 1e-12) > 1.2:
            return "oscillating"
        elif abs(pct_change) < 0.10:
            return "stable"
        elif pct_change < 0:
            return "localizing"
        else:
            return "delocalizing"

    def _classify_transfer(
        self,
        walk_result: WalkResult,
        graph: GraphModel,
    ) -> Tuple[str, Optional[int]]:
        """Classify state transfer quality.

        Uses state_transfer_fidelity if available, otherwise estimates from walk_result.
        - perfect: fidelity > 0.95
        - partial: fidelity 0.30–0.95
        - none: fidelity < 0.30
        """
        fidelity = walk_result.state_transfer_fidelity

        if fidelity is None:
            return "none", None

        if fidelity > 0.95:
            return "perfect", None
        elif fidelity >= 0.30:
            return "partial", None
        else:
            return "none", None

    def _eigenstate_correlation(
        self,
        walk_result: WalkResult,
        graph: GraphModel,
    ) -> Optional[float]:
        """Compute overlap of final state with Laplacian eigenstates."""
        if walk_result.eigenstates is None or walk_result.state_vector_history is None:
            return None
        final_state = walk_result.state_vector_history[-1]
        if final_state is None or walk_result.eigenstates is None:
            return None
        overlaps = np.abs(np.dot(np.conj(walk_result.eigenstates.T), final_state)) ** 2
        return float(np.max(overlaps)) if len(overlaps) > 0 else None
