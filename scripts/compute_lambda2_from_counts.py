#!/usr/bin/env python3
"""Post-processing pass: compute lambda2 from bitstring counts for corpus artifacts.

For each imported artifact (SierpinskiExperimentRecord or HardwareRunRecord):
  1. Build the fractal graph from fractal_graph_nodes (or infer from qubit_count)
  2. Compute spectral gap (lambda2) using the graph eigenproblem solver
  3. Write lambda2 back into observed_metrics["lambda2"]

The fractal_graph_nodes field stores the actual graph node count, which is used as
the primary lookup key into the compiler's known node counts table.
"""

from __future__ import annotations

import sys, json, warnings
from pathlib import Path
from collections import defaultdict

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from gre.fractals.registry import FractalRegistry
from gre.core.graph import GraphModel

warnings.filterwarnings("ignore", message=".*ARPACK.*")
warnings.filterwarnings("ignore", message=".*scipy.sparse.*")

_registry = FractalRegistry()


# ---------------------------------------------------------------------------
# Build node-count → (level, route) lookup from the compiler
# ---------------------------------------------------------------------------

def _build_node_lookup() -> dict[int, list[tuple[str, int]]]:
    """Build a lookup: node_count → [(route, level), ...] from the compiler."""
    lookup: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for route in ["ifs", "pascal_mod2", "rule90", "hanoi"]:
        for level in range(2, 8):
            try:
                geom = _registry.create("sierpinski", level=level, route=route)
                graph = GraphModel.from_geometry(geom)
                nodes = graph.adjacency.shape[0]
                lookup[nodes].append((route, level))
            except Exception:
                pass
    return dict(lookup)


NODE_LOOKUP = _build_node_lookup()
# Also build reverse: (route, level) → node_count
ROUTE_LEVEL_TO_NODES: dict[tuple[str, int], int] = {}
for nodes, pairs in NODE_LOOKUP.items():
    for route, level in pairs:
        ROUTE_LEVEL_TO_NODES[(route, level)] = nodes


# ---------------------------------------------------------------------------
# Lambda2 computation
# ---------------------------------------------------------------------------

_LAMBDA2_CACHE: dict[tuple[str, int], float | None] = {}


def compute_lambda2(level: int, route: str) -> float | None:
    """Derive the fractal graph and compute its spectral gap (lambda2)."""
    key = (route, level)
    if key in _LAMBDA2_CACHE:
        return _LAMBDA2_CACHE[key]

    try:
        geom = _registry.create("sierpinski", level=level, route=route)
        graph = GraphModel.from_geometry(geom)
        sg = graph.spectral_gap()
        result = float(sg) if sg is not None and not np.isnan(sg) else None
    except Exception:
        result = None

    _LAMBDA2_CACHE[key] = result
    return result


# ---------------------------------------------------------------------------
# Fidelity computation from bitstring counts
# ---------------------------------------------------------------------------

def decode_bit_array(meas_b64: str, num_bits: int, n_shots: int) -> dict[int, int]:
    """Decode a numpy-byte-packed BitArray into {bitstring_int: count}.

    IBM Runtime v2 BitArray encoding:
      - decompressed data is a numpy array of shape (n_shots, ceil(num_bits/8)) dtype uint8
      - each row contains 8 packed bits per byte (MSB first)
    """
    import base64, zlib, io

    try:
        raw = base64.b64decode(meas_b64)
        dec = zlib.decompress(raw)
        arr = np.load(io.BytesIO(dec))

        # Ensure shape is (n_shots, n_bytes)
        if arr.ndim == 1:
            arr = arr.reshape(n_shots, -1)
        elif arr.ndim == 2 and arr.shape[0] != n_shots:
            arr = arr.reshape(n_shots, -1)

        n_bytes = arr.shape[1]
        counts: dict[int, int] = defaultdict(int)

        for row in arr:
            val = int.from_bytes(row.tobytes()[:n_bytes], byteorder="big")
            # Mask off unused bits in the top byte
            unused_bits = n_bytes * 8 - num_bits
            if unused_bits:
                val >>= unused_bits
            counts[val] += 1

        return dict(counts)
    except Exception:
        return {}


def compute_fidelity(counts: dict[int, int]) -> float | None:
    """max_count / total as approximate state-transfer fidelity."""
    if not counts:
        return None
    total = sum(counts.values())
    return max(counts.values()) / total if total > 0 else None


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

IMPORTS_DIR = Path(__file__).parent.parent / "imports"


def infer_route_level_from_nodes(node_count: int) -> tuple[str, int] | None:
    """Look up (route, level) from node count."""
    candidates = NODE_LOOKUP.get(node_count, [])
    if not candidates:
        # Try nearest neighbor
        best, best_diff = None, None
        for nodes, pairs in NODE_LOOKUP.items():
            diff = abs(node_count - nodes)
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best = pairs[0] if pairs else None
        return best
    return candidates[0]


def process_sierpinski_record(record_path: Path) -> tuple[bool, dict | None]:
    """Update lambda2 for a SierpinskiExperimentRecord JSON file.

    Uses fractal_graph_nodes as the primary lookup key.
    Falls back to inferring from qubit_count.
    """
    with open(record_path, encoding="utf-8") as f:
        data = json.load(f)

    if ".provenance" in record_path.name:
        return False, None

    level = data.get("recursion_level")
    route = data.get("route", "ifs")

    # Primary key: fractal_graph_nodes
    fgn = data.get("fractal_graph_nodes", 0)

    if fgn and level and route:
        stored_key = (route, level)
        stored_nodes = ROUTE_LEVEL_TO_NODES.get(stored_key)
        if stored_nodes and stored_nodes in NODE_LOOKUP:
            # Stored metadata is self-consistent (route+level → stored_nodes in lookup)
            route, level = stored_key
        elif fgn in NODE_LOOKUP:
            # fgn is in lookup but doesn't match stored (route, level).
            # Use the node-count lookup; stored metadata may be wrong.
            candidates = NODE_LOOKUP[fgn]
            matched = [c for c in candidates if c == stored_key]
            route, level = matched[0] if matched else candidates[0]
        elif stored_nodes and stored_nodes in NODE_LOOKUP:
            # fgn not in lookup but stored (route, level) resolves to a known node count
            route, level = stored_key
        elif stored_nodes:
            # Both lookups fail; fall back to stored metadata anyway
            pass
        else:
            return False, None  # cannot resolve
    elif fgn and fgn in NODE_LOOKUP:
        candidates = NODE_LOOKUP[fgn]
        route, level = candidates[0]
    elif fgn:
        inferred = infer_route_level_from_nodes(fgn)
        if inferred:
            route, level = inferred
        else:
            return False, None
    else:
        return False, None

    lam2 = compute_lambda2(level, route)
    if lam2 is None:
        print(f"  WARN {record_path.name}: lambda2 failed for {route} L{level}")
        return False, None

    obs = data.get("observed_metrics", {})
    if obs.get("lambda2") is not None:
        return False, None

    obs["lambda2"] = lam2
    data["observed_metrics"] = obs
    return True, data


def process_hardware_run_record(record_path: Path) -> tuple[bool, dict | None]:
    """Update lambda2 for a HardwareRunRecord JSON file (fractal_walk family).

    Uses fractal_graph_nodes if available; otherwise infers from qubit_count.
    """
    with open(record_path, encoding="utf-8") as f:
        data = json.load(f)

    if ".provenance" in record_path.name:
        return False, None

    if data.get("circuit_family") != "fractal_walk":
        return False, None

    fgn = data.get("fractal_graph_nodes", 0) or data.get("qubit_count", 0)
    if not fgn or fgn not in NODE_LOOKUP:
        inferred = infer_route_level_from_nodes(fgn) if fgn else None
        if not inferred:
            return False, None
        route, level = inferred
    else:
        candidates = NODE_LOOKUP[fgn]
        route, level = candidates[0] if candidates else infer_route_level_from_nodes(fgn)
        if not route:
            return False, None

    lam2 = compute_lambda2(level, route)
    if lam2 is None:
        return False, None

    obs = data.get("observed_metrics", {})
    if obs.get("lambda2") is not None:
        return False, None

    obs["lambda2"] = lam2
    data["observed_metrics"] = obs
    return True, data


def process_all():
    """Scan all import projects and backfill lambda2."""
    total_changed = total_skipped = total_failed = 0

    for project in ["sierpinski", "qsg", "tmt"]:
        proj_dir = IMPORTS_DIR / project
        if not proj_dir.exists():
            continue

        json_files = [
            f for f in proj_dir.glob("*.json")
            if ".provenance" not in f.name
        ]

        changed = failed = skipped = 0
        for record_path in json_files:
            if project == "sierpinski":
                ok, updated = process_sierpinski_record(record_path)
            else:
                ok, updated = process_hardware_run_record(record_path)

            if ok:
                _write_record(record_path, updated)
                changed += 1
            elif updated is None:
                skipped += 1
            else:
                failed += 1

        print(f"  {project}: {changed} updated, {skipped} skipped, {failed} failed")
        total_changed += changed
        total_skipped += skipped
        total_failed += failed

    print(f"\nTotal: {total_changed} updated, {total_skipped} skipped, {total_failed} failed")
    return total_changed, total_skipped, total_failed


def _write_record(path: Path, data: dict):
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Backfill lambda2 into corpus artifacts")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        _dry_run()
    else:
        process_all()


def _dry_run():
    print("Nodes lookup table:")
    for nodes, pairs in sorted(NODE_LOOKUP.items()):
        for route, level in pairs:
            lam2 = compute_lambda2(level, route)
            print(f"  {nodes:4d} nodes  {route:12s} L{level}: lambda2={lam2:.6f}" if lam2 else f"  {nodes:4d}  {route} L{level}: N/A")
    print()

    for project in ["sierpinski", "qsg", "tmt"]:
        proj_dir = IMPORTS_DIR / project
        if not proj_dir.exists():
            continue
        json_files = [
            f for f in proj_dir.glob("*.json")
            if ".provenance" not in f.name
        ]
        for record_path in json_files:
            if project == "sierpinski":
                ok, _ = process_sierpinski_record(record_path)
            else:
                ok, _ = process_hardware_run_record(record_path)
            if ok:
                print(f"  + {record_path.name}")


if __name__ == "__main__":
    main()
