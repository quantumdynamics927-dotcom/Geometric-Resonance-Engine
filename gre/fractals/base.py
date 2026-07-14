"""Abstract base for fractal geometry generators."""

from abc import ABC, abstractmethod
from typing import List

import numpy as np

from ..core.geometry import GeometryModel


class FractalGenerator(ABC):
    """Abstract base class for all fractal generators.

    All concrete implementations must provide:
    - name: str identifier
    - hausdorff_dimension: float
    - routes: List of independent mathematical derivations
    - generate(level): GeometryModel construction

    Subclasses:
        SierpinskiGenerator - Sierpinski triangle via IFS, Pascal mod 2, Rule 90, etc.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this fractal type."""
        pass

    @property
    @abstractmethod
    def hausdorff_dimension(self) -> float:
        """Theoretical Hausdorff dimension (log(size) / log(scale))."""
        pass

    @abstractmethod
    def routes(self) -> List[str]:
        """List of independent mathematical routes converging on this fractal.

        For Sierpinski: ["pascal_mod2", "rule90", "hanoi", "chaos_game",
                         "ifs", "lucas", "julia"]
        """
        pass

    @abstractmethod
    def generate(self, level: int) -> GeometryModel:
        """Generate fractal geometry at given recursion level.

        Args:
            level: Integer recursion depth (n >= 0)

        Returns:
            GeometryModel with nodes and edges representing the fractal
        """
        pass

    def validate_level(self, level: int) -> None:
        """Validate level parameter.

        Args:
            level: Integer recursion depth.

        Raises:
            ValueError: If level is not a non-negative integer.
        """
        if not isinstance(level, int) or level < 0:
            raise ValueError(
                f"level must be a non-negative integer, got {level!r}"
            )
