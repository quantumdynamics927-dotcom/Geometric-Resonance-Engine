"""Canonical GRC regression fixtures — Sierpinski routes at levels 4-5.

This module provides deterministic compiler fixtures for snapshot and comparison
testing of the Geometric Resonance Compiler (GRC).  All results use
emit_circuits=False to avoid Qiskit runtime dependencies.

Canonical routes and levels
---------------------------
Route        | level=4 | level=5 | strategy    | notes
-------------|---------|---------|-------------|------------------------
ifs         | yes     | yes     | staggered   | IFS affine contractions
pascal_mod2 | yes     | yes     | staggered   | Binomial C(n,k) mod 2
rule90      | yes     | yes     | staggered   | Rule-90 CA evolution
hanoi       | yes     | yes     | staggered   | Tower of Hanoi graph

Fixture data directory
----------------------
Compiled fixture data files (JSON snapshots) are stored in:
    tests/test_compiler_fixtures_data/

Naming convention:
    sierpinski_<route>_level<N>_staggered.json

Example:
    sierpinski_ifs_level4_staggered.json
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple

# Registry and compiler imports
from gre.compiler.compiler import GeometryCompiler
from gre.fractals.registry import FractalRegistry
from gre.compiler.ir import (
    CompilationResult,
    GeometryCompilerConfig,
    ResonanceDescriptor,
    AttractorSignature,
    SymmetrySector,
)


# ---------------------------------------------------------------------------
# Canonical route/level grid
# ---------------------------------------------------------------------------

SIERPINSKI_ROUTES: List[str] = ["ifs", "pascal_mod2", "rule90", "hanoi"]
SIERPINSKI_LEVELS: List[int] = [4, 5]
DEFAULT_STRATEGY: str = "staggered"


# ---------------------------------------------------------------------------
# Compiler singleton (shared across fixture calls for speed)
# ---------------------------------------------------------------------------

_ENGINE: Optional[GeometryCompiler] = None


def _get_engine() -> GeometryCompiler:
    """Return a shared GeometryCompiler instance configured for fixture use."""
    global _ENGINE
    if _ENGINE is None:
        config = GeometryCompilerConfig(
            emit_circuits=False,   # Avoid Qiskit dependency in fixtures
            compute_symmetry=True,
            compute_multiscale=True,
            walk_steps=20,
            initial_node=0,
            strategies=[DEFAULT_STRATEGY],
        )
        _ENGINE = GeometryCompiler(config)
    return _ENGINE


# ---------------------------------------------------------------------------
# Core fixture helper
# ---------------------------------------------------------------------------

def get_canonical_result(
    route: str,
    level: int = 4,
    strategy: str = DEFAULT_STRATEGY,
) -> Dict[str, Any]:
    """Return a serializable canonical summary for a route+level+strategy combination.

    Parameters
    ----------
    route : str
        Sierpinski mathematical route.  One of "ifs", "pascal_mod2", "rule90",
        "hanoi".
    level : int
        Recursion depth.  Default 4.  Level 5 is also supported.
    strategy : str
        Quantum-walk strategy.  Default "staggered".

    Returns
    -------
    dict
        Canonical summary dict with the following keys::

            spectral_gap                  (float)
            eigenvalue_spacing_ratio      (float)
            resonance_frequency           (float)
            resonance_coupling            (float)
            average_degree                (float)
            golden_ratio_ratio            (float)
            attractor_label               (str)
            entropy_rate                  (float)
            entropy_trajectory            (str)
            participation_ratio_final     (float)
            participation_ratio_trend    (str)
            transfer_class                (str)
            symmetry_automorphism_invariant (bool)
            symmetry_color_count          (int)
            multiscale_cluster_count      (int)

        Plus metadata fields::

            source_id        (str)
            compile_time_ms  (float)
            route            (str)
            level            (int)
            strategy         (str)

    Raises
    ------
    ValueError
        If ``route`` or ``level`` is not in the canonical grid.
    """
    # Validate inputs early so fixture generation fails fast
    if route not in SIERPINSKI_ROUTES:
        raise ValueError(
            f"Unknown route {route!r}.  Canonical routes: {SIERPINSKI_ROUTES}"
        )
    if level not in SIERPINSKI_LEVELS:
        raise ValueError(
            f"Unsupported level {level}.  Canonical levels: {SIERPINSKI_LEVELS}"
        )
    if strategy != DEFAULT_STRATEGY:
        raise ValueError(
            f"Canonical strategy is fixed at {DEFAULT_STRATEGY!r}; got {strategy!r}"
        )

    # Compile (shared engine, emit_circuits=False)
    compiler = _get_engine()
    result: CompilationResult = compiler.compile(
        geometry="sierpinski",
        route=route,
        level=level,
        strategies=[strategy],
        emit_circuits=False,
    )

    return _result_to_summary(result, route=route, level=level, strategy=strategy)


def _result_to_summary(
    result: CompilationResult,
    route: str,
    level: int,
    strategy: str,
) -> Dict[str, Any]:
    """Convert a CompilationResult into the flat canonical summary dict."""

    # Primary walk result (staggered)
    strat_result = result.walk_results[strategy]
    resonance: ResonanceDescriptor = strat_result.resonance_descriptor
    attractor: AttractorSignature = strat_result.attractor_signature

    # Symmetry sector
    symmetry: Optional[SymmetrySector] = result.symmetry_sector
    symmetry_invariant: bool = symmetry.automorphism_invariant if symmetry else False
    symmetry_color_count: int = len(symmetry.sector_counts) if symmetry else 0

    # Multiscale partition
    partition = result.multiscale_partition
    cluster_count: int = len(partition.clusters) if partition else 0

    summary: Dict[str, Any] = {
        # Resonance descriptor fields
        "spectral_gap": float(resonance.spectral_gap),
        "eigenvalue_spacing_ratio": float(resonance.eigenvalue_spacing_ratio),
        "resonance_frequency": float(resonance.resonance_frequency),
        "resonance_coupling": float(resonance.resonance_coupling),
        "average_degree": float(resonance.average_degree),
        "golden_ratio_ratio": float(resonance.golden_ratio_ratio),

        # Attractor signature fields
        "attractor_label": str(attractor.attractor_label),
        "entropy_rate": float(attractor.entropy_rate),
        "entropy_trajectory": str(attractor.entropy_trajectory),
        "participation_ratio_final": float(attractor.participation_ratio_final),
        "participation_ratio_trend": str(attractor.participation_ratio_trend),
        "transfer_class": str(attractor.transfer_class),

        # Symmetry sector fields
        "symmetry_automorphism_invariant": bool(symmetry_invariant),
        "symmetry_color_count": int(symmetry_color_count),

        # Multiscale partition fields
        "multiscale_cluster_count": int(cluster_count),

        # Metadata (useful for fixture introspection and diffing)
        "source_id": str(result.source_id),
        "compile_time_ms": float(result.compile_time_ms),
        "route": route,
        "level": level,
        "strategy": strategy,
    }

    return summary


# ---------------------------------------------------------------------------
# Convenience accessors for common (route, level) pairs
# ---------------------------------------------------------------------------

# Level 4
def sierpinski_ifs_level4() -> Dict[str, Any]:
    """Canonical result: Sierpinski IFS, level 4, staggered walk."""
    return get_canonical_result("ifs", level=4)


def sierpinski_pascal_mod2_level4() -> Dict[str, Any]:
    """Canonical result: Sierpinski Pascal-mod-2, level 4, staggered walk."""
    return get_canonical_result("pascal_mod2", level=4)


def sierpinski_rule90_level4() -> Dict[str, Any]:
    """Canonical result: Sierpinski Rule-90, level 4, staggered walk."""
    return get_canonical_result("rule90", level=4)


def sierpinski_hanoi_level4() -> Dict[str, Any]:
    """Canonical result: Sierpinski Hanoi, level 4, staggered walk."""
    return get_canonical_result("hanoi", level=4)


# Level 5
def sierpinski_ifs_level5() -> Dict[str, Any]:
    """Canonical result: Sierpinski IFS, level 5, staggered walk."""
    return get_canonical_result("ifs", level=5)


def sierpinski_pascal_mod2_level5() -> Dict[str, Any]:
    """Canonical result: Sierpinski Pascal-mod-2, level 5, staggered walk."""
    return get_canonical_result("pascal_mod2", level=5)


def sierpinski_rule90_level5() -> Dict[str, Any]:
    """Canonical result: Sierpinski Rule-90, level 5, staggered walk."""
    return get_canonical_result("rule90", level=5)


def sierpinski_hanoi_level5() -> Dict[str, Any]:
    """Canonical result: Sierpinski Hanoi, level 5, staggered walk."""
    return get_canonical_result("hanoi", level=5)


# ---------------------------------------------------------------------------
# All canonical results as a grid (useful for batch regression)
# ---------------------------------------------------------------------------

CANONICAL_GRID: Dict[Tuple[str, int], Dict[str, Any]] = {}


def _build_canonical_grid() -> None:
    """Populate CANONICAL_GRID with all (route, level) combinations.

    Call this explicitly in tests that need the full grid without triggering
    compilation at module import time.
    """
    for route in SIERPINSKI_ROUTES:
        for level in SIERPINSKI_LEVELS:
            key = (route, level)
            CANONICAL_GRID[key] = get_canonical_result(route, level)


# ---------------------------------------------------------------------------
# Pytest fixture hooks (consume via `from tests.test_compiler_fixtures import ...`)
# ---------------------------------------------------------------------------

def pytest_configure(config) -> None:
    """Pre-populate CANONICAL_GRID when pytest collects this module."""
    _build_canonical_grid()
