"""Graph-theoretic representations derived from fractal geometry."""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import eigsh

from .geometry import GeometryModel


@dataclass
class GraphModel:
    """Graph structure derived from a fractal geometry.

    Attributes:
        adjacency: (N, N) adjacency matrix. adj[i,j] = edge weight or 0.
        laplacian: (N, N) combinatorial Laplacian L = D - A.
        eigenpairs: Dict mapping eigenvalue → eigenvector array.
        degree: (N,) array of node degrees.
    """

    adjacency: np.ndarray
    laplacian: np.ndarray
    eigenpairs: Dict[float, np.ndarray] = None
    degree: np.ndarray = None

    def __post_init__(self):
        n = self.adjacency.shape[0]
        if self.adjacency.shape != (n, n):
            raise ValueError("adjacency must be square")
        if self.degree is None:
            self.degree = np.sum(self.adjacency, axis=1)
        if self.laplacian is None:
            D = np.diag(self.degree)
            self.laplacian = D - self.adjacency
        if self.eigenpairs is None:
            self.eigenpairs = {}

    @classmethod
    def from_geometry(cls, geometry: GeometryModel) -> "GraphModel":
        """Derive graph structure from fractal geometry topology.

        Nodes become graph vertices; edges become undirected weighted edges.
        Contraction edges and lateral edges both get weight 1.0.

        Args:
            geometry: GeometryModel instance.

        Returns:
            GraphModel with computed adjacency and Laplacian.
        """
        n = len(geometry.nodes)
        adj = np.zeros((n, n), dtype=np.float64)

        for edge in geometry.edges:
            adj[edge.source, edge.target] = edge.weight
            adj[edge.target, edge.source] = edge.weight  # Undirected

        return cls(adjacency=adj, laplacian=None, eigenpairs={})

    def compute_eigenpairs(self, k: int = 10) -> Tuple[np.ndarray, np.ndarray]:
        """Compute k smallest eigenvalues and eigenvectors of the Laplacian.

        Args:
            k: Number of eigenpairs to compute (default 10).

        Returns:
            Tuple of (eigenvalues, eigenvectors) where:
            - eigenvalues: shape (k,) array of smallest eigenvalues
            - eigenvectors: shape (N, k) array, column i is eigenvector for eigenvalues[i]
        """
        n = self.adjacency.shape[0]
        k = min(k, n - 1)

        # Use sparse eigsh for efficiency
        L_sparse = sparse.csr_matrix(self.laplacian)
        eigenvalues, eigenvectors = eigsh(L_sparse, k=k, which="SM")

        # Store in eigenpairs dict
        for i, ev in enumerate(eigenvalues):
            self.eigenpairs[ev] = eigenvectors[:, i]

        return eigenvalues, eigenvectors

    def effective_resistance(self, i: int, j: int) -> float:
        """Compute effective resistance between nodes i and j.

        Uses Laplacian pseudoinverse:
        R_ij = (L^+)_ii + (L^+)_jj - 2(L^+)_ij

        Args:
            i: Source node index.
            j: Target node index.

        Returns:
            Effective resistance R_ij as a float.
        """
        n = self.adjacency.shape[0]
        if i == j:
            return 0.0

        # Full eigendecomposition of Laplacian
        eigenvalues, eigenvectors = np.linalg.eigh(self.laplacian)

        # Pseudoinverse: L^+ = V Λ^+ V^T (add small regularization to avoid /0)
        eigenvalues_reg = eigenvalues + 1e-12
        L_pinv = eigenvectors @ np.diag(1.0 / eigenvalues_reg) @ eigenvectors.T

        return float(L_pinv[i, i] + L_pinv[j, j] - 2 * L_pinv[i, j])

    def spectral_gap(self) -> float:
        """Return λ₂ of Laplacian — stability indicator.

        Larger spectral gap → more stable oscillations, less prone to
        decoherence or localization.

        Returns:
            Second-smallest eigenvalue of Laplacian (λ₂).
        """
        eigenvalues, _ = self.compute_eigenpairs(k=2)
        if len(eigenvalues) > 1:
            return float(eigenvalues[1])
        return 0.0

    def degree_distribution(self) -> np.ndarray:
        """Return (N,) array of degrees for each node."""
        return self.degree

    def adjacency_spectrum(self) -> np.ndarray:
        """Return eigenvalues of the adjacency matrix."""
        return np.linalg.eigvalsh(self.adjacency)

    def adjacency_list(self) -> List[List[int]]:
        """Return adjacency as list of neighbor lists."""
        n = self.adjacency.shape[0]
        result: List[List[int]] = [[] for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if self.adjacency[i, j] > 0:
                    result[i].append(j)
        return result
