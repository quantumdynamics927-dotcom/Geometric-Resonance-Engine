from ..ir import CompilationResult
from typing import Optional


class CircuitModelEmitter:
    """Emit CircuitModel from CompilationResult."""

    def emit(self, result: CompilationResult, strategy: str = "staggered") -> Optional["CircuitModel"]:
        """Return CircuitModel if already built during compilation."""
        if strategy not in result.walk_results:
            return None

        return result.walk_results[strategy].circuit
