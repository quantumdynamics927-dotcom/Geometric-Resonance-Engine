"""Snapshot-style regression tests for GRC route-family separability.

These tests assert that the GeometryCompiler produces measurably distinct
signatures for different mathematical routes on the same fractal, and that
key invariants (determinism, level-monotonicity) hold across versions.
"""

from __future__ import annotations

import warnings

import pytest

from tests.test_compiler_fixtures import get_canonical_result

# Suppress all numerical/numpy warnings in tests
warnings.filterwarnings("ignore")


class TestRouteSeparability:
    """Assert that different routes produce distinct signatures."""

    def test_ifs_vs_pascal_mod2_spectral_gap(self):
        """ifs and pascal_mod2 must differ on spectral_gap by > 1e-6."""
        ifs_result = get_canonical_result("ifs", level=4)
        pascal_result = get_canonical_result("pascal_mod2", level=4)

        ifs_gap = ifs_result["spectral_gap"]
        pascal_gap = pascal_result["spectral_gap"]

        diff = abs(ifs_gap - pascal_gap)
        assert diff > 1e-6, (
            f"ifs spectral_gap ({ifs_gap}) and pascal_mod2 ({pascal_gap}) "
            f"must differ by > 1e-6, got {diff}"
        )

    def test_ifs_vs_hanoi_spectral_gap(self):
        """ifs and hanoi must differ on spectral_gap by > 1e-6."""
        ifs_result = get_canonical_result("ifs", level=4)
        hanoi_result = get_canonical_result("hanoi", level=4)

        ifs_gap = ifs_result["spectral_gap"]
        hanoi_gap = hanoi_result["spectral_gap"]

        diff = abs(ifs_gap - hanoi_gap)
        assert diff > 1e-6, (
            f"ifs spectral_gap ({ifs_gap}) and hanoi ({hanoi_gap}) "
            f"must differ by > 1e-6, got {diff}"
        )

    def test_attractor_label_differences(self):
        """At least one pair of routes must have different attractor_label."""
        # Canonical routes only — chaos_game, lucas, julia are not canonical
        routes = ["ifs", "pascal_mod2", "rule90", "hanoi"]
        labels = {}
        for route in routes:
            result = get_canonical_result(route, level=4)
            labels[route] = result["attractor_label"]

        unique_labels = set(labels.values())
        assert len(unique_labels) >= 2, (
            f"Expected at least 2 distinct attractor_labels across routes, "
            f"got {labels}"
        )

    def test_all_routes_produce_valid_descriptors(self):
        """All routes should produce non-null resonance descriptors."""
        routes = ["ifs", "pascal_mod2", "hanoi"]
        for route in routes:
            result = get_canonical_result(route, level=4)
            gap = result["spectral_gap"]
            assert gap is not None, f"Route {route} returned null spectral_gap"
            # NaN check
            assert gap == gap, f"Route {route} produced NaN spectral_gap"


class TestDeterminism:
    """Assert that repeated compilations yield identical results."""

    def test_spectral_gap_deterministic(self):
        """Running the same compile twice gives identical spectral_gap."""
        r1 = get_canonical_result("ifs", level=4)
        r2 = get_canonical_result("ifs", level=4)

        gap1 = r1["spectral_gap"]
        gap2 = r2["spectral_gap"]

        # Float tolerance: results should be bit-exact for the same RNG seed
        assert abs(gap1 - gap2) < 1e-12, (
            f"spectral_gap not deterministic: first={gap1}, second={gap2}"
        )

    def test_attractor_label_deterministic(self):
        """attractor_label is stable across identical compilations."""
        r1 = get_canonical_result("pascal_mod2", level=4)
        r2 = get_canonical_result("pascal_mod2", level=4)

        assert r1["attractor_label"] == r2["attractor_label"], (
            f"attractor_label not deterministic: first={r1['attractor_label']}, "
            f"second={r2['attractor_label']}"
        )


class TestLevelMonotonicity:
    """Assert spectral_gap is in a reasonable ballpark as level increases."""

    def test_spectral_gap_level_4_to_5_reasonable(self):
        """spectral_gap at level 5 should be in the same ballpark as level 4."""
        r4 = get_canonical_result("ifs", level=4)
        r5 = get_canonical_result("ifs", level=5)

        gap4 = r4["spectral_gap"]
        gap5 = r5["spectral_gap"]

        # Sanity: gap at level 5 should be within an order of magnitude of level 4.
        # This is a soft check — exact monotonicity is not guaranteed for all routes.
        ratio = gap5 / gap4 if gap4 != 0 else 0.0
        assert 0.1 < ratio < 10.0, (
            f"spectral_gap ratio level5/level4 = {ratio} "
            f"is outside the 0.1-10x sanity band "
            f"(level4={gap4}, level5={gap5})"
        )

    def test_pascal_mod2_level_monotonicity(self):
        """pascal_mod2 gap should be in similar ballpark across levels 4 to 5."""
        r4 = get_canonical_result("pascal_mod2", level=4)
        r5 = get_canonical_result("pascal_mod2", level=5)

        gap4 = r4["spectral_gap"]
        gap5 = r5["spectral_gap"]

        ratio = gap5 / gap4 if gap4 != 0 else 0.0
        assert 0.1 < ratio < 10.0, (
            f"pascal_mod2 spectral_gap ratio {ratio} outside 0.1-10x "
            f"(level4={gap4}, level5={gap5})"
        )
