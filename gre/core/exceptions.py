"""Core exception hierarchy."""

class GREError(Exception):
    """Base exception for all GRE errors."""
    pass


class GeometryGenerationError(GREError):
    """Raised when fractal geometry generation fails."""
    pass


class GraphComputationError(GREError):
    """Raised when graph computation (eigenpairs, laplacian, etc.) fails."""
    pass


class CircuitMappingError(GREError):
    """Raised when graph-to-circuit mapping fails."""
    pass


class HardwareExecutionError(GREError):
    """Raised when hardware execution fails."""
    pass


class ValidationError(GREError):
    """Raised when input validation fails."""
    pass
