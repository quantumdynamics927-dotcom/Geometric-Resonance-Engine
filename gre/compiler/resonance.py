from ..core.graph import GraphModel
from ..simulation.quantum_walk import WalkResult
from ..quantum.gates import FractalGateLibrary
from .ir import ResonanceDescriptor
from typing import Dict, Tuple
import numpy as np


class ResonanceDescriptorComputer:
    """Extract resonance descriptor from a compiled graph + walk result.

    Combines spectral features from graph eigenpairs with fractal gate parameters.
    """

    def compute(self, graph: GraphModel, walk_result: WalkResult) -> ResonanceDescriptor:
        # 1. Eigenpairs — request k = min(10, n) or as many as available
        n = graph.adjacency.shape[0]
        k = min(10, n)
        eigenvalues = np.array([])
        eigenvectors = np.zeros((n, 0))
        try:
            # Provide a random starting vector to avoid ARPACK zero-vector failures
            v0 = np.random.default_rng(42).standard_normal(n)
            v0 = v0 / (np.linalg.norm(v0) + 1e-12)
            eigenvalues, eigenvectors = graph.compute_eigenpairs(k, v0=v0)
        except Exception:
            # Fall back to adjacency spectrum if Laplacian eigenpairs fail
            try:
                eigenvalues, eigenvectors = graph.adjacency_spectrum()
                eigenvalues = eigenvalues[:k]
                eigenvectors = eigenvectors[:, :k] if eigenvectors.shape[1] >= k else eigenvectors
            except Exception:
                eigenvalues = np.array([])
                eigenvectors = np.zeros((n, 0))

        # 2. Spectral moments
        spectral_moments = self._spectral_moments(eigenvalues)

        # 3. Spectral gap (λ₂ of Laplacian)
        spectral_gap = graph.spectral_gap()

        # 4. Eigenvalue spacing ratio (λ₂/λ₃ of Laplacian — level-spacing indicator)
        eigenvalue_spacing_ratio = 0.0
        if len(eigenvalues) >= 3:
            eigenvalue_spacing_ratio = eigenvalues[1] / eigenvalues[2] if eigenvalues[2] != 0 else 0.0

        # 5. Resonance gate parameters (infer from walk oscillation pattern)
        resonance_frequency, resonance_coupling, num_bands = self._infer_resonance(walk_result)

        # 6. Fixed-point angles from FractalGateLibrary.sierpinski_fixed_point_gate
        # Approximate: use eigenvalue phases from eigenvectors
        fixed_point_angles = self._extract_fixed_point_angles(eigenvectors)

        # 7. Golden ratio ratio: how close is the fixed-point angle to 1/φ?
        golden_ratio_ratio = self._compute_golden_ratio_ratio(fixed_point_angles)

        # 8. Degree distribution
        degree_dist = graph.degree_distribution()
        avg_degree = float(np.mean(degree_dist)) if len(degree_dist) > 0 else 0.0

        return ResonanceDescriptor(
            eigenvalues=eigenvalues,
            spectral_moments=spectral_moments,
            spectral_gap=spectral_gap,
            eigenvalue_spacing_ratio=eigenvalue_spacing_ratio,
            resonance_frequency=resonance_frequency,
            resonance_coupling=resonance_coupling,
            num_resonance_bands=num_bands,
            fixed_point_angles=fixed_point_angles,
            golden_ratio_ratio=golden_ratio_ratio,
            degree_distribution=degree_dist,
            average_degree=avg_degree,
        )

    def _spectral_moments(self, eigenvalues: np.ndarray) -> Dict[str, float]:
        """Compute mean, variance, skewness, kurtosis of eigenvalue distribution."""
        if len(eigenvalues) == 0:
            return {"mean": 0.0, "variance": 0.0, "skewness": 0.0, "kurtosis": 0.0}
        # Normalize to [0, 1] for stable moment computation
        e_min, e_max = eigenvalues.min(), eigenvalues.max()
        if e_max == e_min:
            return {"mean": float(eigenvalues.mean()), "variance": 0.0, "skewness": 0.0, "kurtosis": 0.0}
        e_norm = (eigenvalues - e_min) / (e_max - e_min)
        m1 = float(e_norm.mean())
        m2 = float(np.var(e_norm))
        # Skewness: third standardized moment
        m3 = float(np.mean(((e_norm - m1) / (np.sqrt(m2) + 1e-12)) ** 3)) if m2 > 0 else 0.0
        # Kurtosis: fourth standardized moment - 3 (excess)
        m4 = float(np.mean(((e_norm - m1) / (np.sqrt(m2) + 1e-12)) ** 4)) - 3.0 if m2 > 0 else 0.0
        return {"mean": m1, "variance": m2, "skewness": m3, "kurtosis": m4}

    def _infer_resonance(self, walk_result: WalkResult) -> Tuple[float, float, int]:
        """Infer resonance_frequency, coupling, and num_bands from walk oscillation.

        Uses early-time participation ratio growth to estimate coupling.
        Frequency inferred from state_vector_history oscillation via FFT.
        Returns defaults if insufficient data.
        """
        # Default resonance parameters (can be refined with actual walk data)
        resonance_frequency = 0.5  # Default
        resonance_coupling = 0.1  # Default
        num_bands = 3

        if walk_result.state_vector_history is not None:
            history = walk_result.state_vector_history
            if len(history) >= 4:
                # Compute participation ratio trajectory
                pr_traj = []
                for state in history:
                    probs = np.abs(state) ** 2
                    pr = float(np.sum(probs ** 2))  # Inverse participation ratio
                    pr_traj.append(pr)

                # Guard against NaN from degenerate graph states (e.g. isolated nodes)
                if not np.all(np.isfinite(pr_traj)):
                    return resonance_frequency, resonance_coupling, num_bands

                # Growth rate of PR → coupling strength proxy
                # Guard against all-zero initial state (zero-division)
                if len(pr_traj) >= 2 and pr_traj[0] > 0:
                    growth = (pr_traj[-1] - pr_traj[0]) / pr_traj[0]
                    resonance_coupling = float(np.clip(abs(growth) / len(pr_traj), 0.01, 1.0))
                elif len(pr_traj) >= 2:
                    # Initial state was degenerate (zero amplitude); use total variation as proxy
                    tv = float(np.sum(np.abs(np.diff(pr_traj))))
                    resonance_coupling = float(np.clip(tv / len(pr_traj), 0.01, 1.0))

                # FFT of PR trajectory → dominant frequency
                if len(pr_traj) >= 4:
                    fft_vals = np.abs(np.fft.rfft(np.array(pr_traj)))
                    if len(fft_vals) > 1:
                        dom_idx = np.argmax(fft_vals[1:]) + 1  # Skip DC
                        dom_freq = dom_idx / len(pr_traj)
                        resonance_frequency = float(dom_freq)

        return resonance_frequency, resonance_coupling, num_bands

    def _extract_fixed_point_angles(self, eigenvectors: np.ndarray) -> np.ndarray:
        """Extract eigenvalue phases from eigenvectors — approximate fixed-point angles.

        For Sierpinski, the golden ratio 1/φ ≈ 0.618 appears in eigenvalue phases.
        """
        if eigenvectors is None or eigenvectors.size == 0:
            return np.array([])
        # Handle both (n,) and (n, k) shapes
        ev = eigenvectors[:, 0] if eigenvectors.ndim == 2 and eigenvectors.shape[1] > 0 else eigenvectors
        phases = np.angle(ev)
        return phases

    def _compute_golden_ratio_ratio(self, fixed_point_angles: np.ndarray) -> float:
        """Compute how close the observed phase ratio is to 1/φ ≈ 0.618."""
        if len(fixed_point_angles) == 0:
            return 0.0
        PHI = 0.6180339887498949
        mean_angle = float(np.mean(np.abs(fixed_point_angles)))
        if mean_angle == 0:
            return 0.0
        ratio = mean_angle / PHI
        return ratio  # 1.0 means perfect match
