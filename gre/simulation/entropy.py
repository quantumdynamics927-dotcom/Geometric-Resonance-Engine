"""Entropy metrics for fractal graph states and structures."""

from typing import Optional

import numpy as np

from ..core.geometry import GeometryModel
from ..core.graph import GraphModel


def shannon_entropy(probability_distribution: np.ndarray, base: float = 2.0) -> float:
    """Compute Shannon entropy H = -Σ p log(p).

    Args:
        probability_distribution: Array of probabilities (will be normalized).
        base: Logarithm base. 2.0 = bits, np.e = nats, 10.0 = dits.

    Returns:
        Shannon entropy H in units of the chosen base.
    """
    p = np.asarray(probability_distribution, dtype=np.float64)
    p = p[p > 1e-15]  # Avoid log(0)
    p = p / np.sum(p)  # Normalize

    return float(-np.sum(p * np.log(p) / np.log(base)))


def von_neumann_entropy(density_matrix: np.ndarray) -> float:
    """Compute von Neumann entropy S = -Tr(ρ log ρ).

    Args:
        density_matrix: (N, N) density matrix (should be Hermitian, positive semi-definite).

    Returns:
        Von Neumann entropy in nats.
    """
    # Eigenvalues of density matrix
    eigenvals = np.linalg.eigvalsh(density_matrix)
    eigenvals = eigenvals[eigenvals > 1e-12]  # Avoid log(0)
    return float(-np.sum(eigenvals * np.log(eigenvals)))


def topological_entropy(geometry: GeometryModel) -> float:
    """Estimate topological entropy from fractal geometry.

    Topological entropy quantifies the growth rate of distinct
    geometric patterns with recursion depth. For self-similar fractals,
    it relates to the Hausdorff dimension and the number of self-similar
    pieces.

    H_top ≈ log(#self-similar_pieces) / log(1/scale_factor)

    For Sierpinski: H_top ≈ log(3) / log(2) = Hausdorff dimension

    Args:
        geometry: GeometryModel for the fractal.

    Returns:
        Estimated topological entropy.
    """
    meta = geometry.meta

    # For self-similar fractals: H_top = log(N_pieces) / log(1/scale)
    # Sierpinski: 3 pieces at scale 1/2 → log(3)/log(2)
    if meta.fractal_type == "sierpinski":
        # Each level: 3^level triangles, scale factor 1/2
        return float(np.log(3) / np.log(2))

    # Fallback: use boundary growth rate
    if meta.level > 0 and meta.enclosed_area > 0:
        boundary_rate = meta.boundary_length / (meta.enclosed_area ** (1.0 / 2))
        return float(np.log(max(boundary_rate, 1)) * meta.hausdorff_dimension)
    else:
        return float(meta.hausdorff_dimension)


def conditional_entropy_region(
    probabilities: np.ndarray,
    region_mask: np.ndarray
) -> float:
    """Compute conditional entropy H(region | complement).

    H(X|Y) = H(X,Y) - H(Y)
    where X is the region and Y is its complement.

    This measures how much entropy is confined within a region vs spread
    across the boundary — useful for analyzing void/decoherence-free subspaces.

    Args:
        probabilities: (N,) probability distribution over all nodes.
        region_mask: (N,) boolean array, True for nodes in the region.

    Returns:
        Conditional entropy H(region | complement) in bits.
    """
    p = np.asarray(probabilities, dtype=np.float64)
    mask = np.asarray(region_mask, dtype=bool)

    # Normalize
    p = p / np.sum(p)

    p_region = p[mask]
    p_complement = p[~mask]

    # Total entropy
    H_total = shannon_entropy(p)

    # Entropy of region distribution (conditioned on being in region)
    p_region_norm = p_region / np.sum(p_region) if np.sum(p_region) > 0 else p_region
    H_region = shannon_entropy(p_region_norm) if np.sum(p_region) > 0 else 0.0

    # Marginal entropy of choosing region vs complement
    P_region = np.sum(p_region)
    P_complement = np.sum(p_complement)

    if P_region > 0 and P_complement > 0:
        H_marginal = shannon_entropy(np.array([P_region, P_complement]))
    else:
        H_marginal = 0.0

    # Joint entropy H(region, complement)
    H_joint = H_total

    # Conditional: H(region | complement) = H_joint - H(complement)
    # Or equivalently: P(region) * H(region | in region)
    H_conditional = H_joint - shannon_entropy(np.array([P_complement, P_region]))

    return float(H_conditional)


def uniform_distribution_entropy(n: int, base: float = 2.0) -> float:
    """Maximum entropy for n outcomes (uniform distribution).

    Args:
        n: Number of possible outcomes.
        base: Logarithm base.

    Returns:
        Maximum entropy = log_b(n).
    """
    if n <= 0:
        return 0.0
    return float(np.log(n) / np.log(base))


def purity(density_matrix: np.ndarray) -> float:
    """Compute purity of a density matrix: Tr(ρ²).

    Purity = 1 for pure states, → 0 for maximally mixed states.

    Args:
        density_matrix: (N, N) density matrix.

    Returns:
        Purity Tr(ρ²) as a float in [0, 1].
    """
    return float(np.trace(density_matrix @ density_matrix).real)


def linear_entropy(density_matrix: np.ndarray) -> float:
    """Compute linear entropy (simplified version of von Neumann).

    S_linear = 1 - Tr(ρ²)
    Approximates von Neumann entropy for nearly pure states.

    Args:
        density_matrix: (N, N) density matrix.

    Returns:
        Linear entropy in nats.
    """
    return float(1 - purity(density_matrix))
