"""Fractal generator factory and registry."""

from typing import Dict, Type, List

from .base import FractalGenerator
from .sierpinski import SierpinskiGenerator


class FractalRegistry:
    """Factory for creating fractal geometries by name.

    Usage:
        geometry = FractalRegistry.create("sierpinski", level=5, route="ifs")
        info = FractalRegistry.fractal_info("sierpinski")

    Adding a new fractal:
        class KochGenerator(FractalGenerator):
            ...

        FractalRegistry.register(KochGenerator)
        geometry = FractalRegistry.create("koch", level=4)
    """

    _fractals: Dict[str, Type[FractalGenerator]] = {}
    _initialized: bool = False

    @classmethod
    def _initialize(cls) -> None:
        """Register built-in fractals."""
        if cls._initialized:
            return
        cls.register(SierpinskiGenerator)
        cls._initialized = True

    @classmethod
    def register(cls, fractal_class: Type[FractalGenerator]) -> None:
        """Register a fractal generator class.

        Args:
            fractal_class: Subclass of FractalGenerator.
        """
        instance = fractal_class()
        cls._fractals[instance.name] = fractal_class

    @classmethod
    def create(
        cls,
        name: str,
        level: int,
        route: str = "ifs",
        **kwargs
    ) -> "GeometryModel":
        """Create a fractal geometry by name.

        Args:
            name: Fractal identifier (e.g., "sierpinski", "koch").
            level: Recursion depth.
            route: Mathematical route for generation (fractal-dependent).
            **kwargs: Additional arguments passed to the generator.

        Returns:
            GeometryModel instance.

        Raises:
            ValueError: If fractal name is not registered.
        """
        cls._initialize()

        if name not in cls._fractals:
            available = list(cls._fractals.keys())
            raise ValueError(
                f"Unknown fractal '{name}'. Available: {available}"
            )

        generator = cls._fractals[name](route=route, **kwargs)
        return generator.generate(level)

    @classmethod
    def list_fractals(cls) -> List[str]:
        """List all registered fractal type names."""
        cls._initialize()
        return list(cls._fractals.keys())

    @classmethod
    def fractal_info(cls, name: str) -> Dict:
        """Get information about a registered fractal type.

        Args:
            name: Fractal identifier.

        Returns:
            Dict with keys: name, hausdorff_dimension, routes.

        Raises:
            ValueError: If fractal name is not registered.
        """
        cls._initialize()

        if name not in cls._fractals:
            raise ValueError(f"Unknown fractal '{name}'")

        generator = cls._fractals[name]()
        return {
            "name": generator.name,
            "hausdorff_dimension": generator.hausdorff_dimension,
            "routes": generator.routes()
        }
