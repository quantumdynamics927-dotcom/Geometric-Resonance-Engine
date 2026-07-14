"""Research corpus management and query/filter API.

The corpus is the central store for all imported hardware runs, experiments,
and calibration snapshots. It provides query methods to filter by
backend, depth, project, hypothesis tag, and date range.

Usage:
    corpus = ResearchCorpus()
    corpus.load_directory("imports/qsg")
    corpus.load_directory("imports/sierpinski")

    # Query methods
    runs = corpus.find_runs(backend="ibmq_qasm_simulator", depth=5)
    experiments = corpus.find_sierpinski_experiments(recursion_level=5)
    calibrations = corpus.find_calibrations(backend="ibm_perth")

    # Comparison
    match = corpus.compare_generated_to_history(
        graph_nodes=27,
        depth=5,
        backend="ibmq_qasm_simulator"
    )
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
import json
import os
import glob
from pathlib import Path

from .schemas import (
    HardwareRunRecord,
    SierpinskiExperimentRecord,
    CalibrationSnapshot,
    ExperimentTag,
    CircuitFamily,
)
from .provenance import ProvenanceSidecar
from .artifacts import ArtifactRegistry


# -----------------------------------------------------------------------------
# Corpus storage
# -----------------------------------------------------------------------------

@dataclass
class CorpusStats:
    """Statistics about the current corpus state."""
    total_runs: int = 0
    total_sierpinski_experiments: int = 0
    total_calibrations: int = 0
    projects: List[str] = field(default_factory=list)
    backends: List[str] = field(default_factory=list)
    depth_range: tuple = field(default=lambda: (0, 0))
    date_range: tuple = field(default=lambda: ("", ""))


class ResearchCorpus:
    """Central store for all imported research records.

    The corpus maintains three separate registries:
    - hardware_runs: HardwareRunRecord instances
    - sierpinski_experiments: SierpinskiExperimentRecord instances
    - calibrations: CalibrationSnapshot instances

    Records are loaded from JSON files and can be queried by any field.

    Artifacts (raw data files) are tracked via an ArtifactRegistry.
    """

    def __init__(self):
        self.hardware_runs: Dict[str, HardwareRunRecord] = {}
        self.sierpinski_experiments: Dict[str, SierpinskiExperimentRecord] = {}
        self.calibrations: Dict[str, CalibrationSnapshot] = {}
        self.artifact_registry = ArtifactRegistry()
        self._stats = CorpusStats()

    # -------------------------------------------------------------------------
    # Load from disk
    # -------------------------------------------------------------------------

    def load_directory(self, path: str) -> int:
        """Load all records from a directory of JSON files.

        Recursively scans the directory for .json files and attempts
        to parse them as HardwareRunRecord, SierpinskiExperimentRecord,
        or CalibrationSnapshot based on their schema.

        Args:
            path: Absolute or relative path to the directory.

        Returns:
            Number of records loaded.
        """
        loaded = 0
        for root, _, files in os.walk(path):
            for fname in files:
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    n = self._load_file(fpath)
                    loaded += n
                except Exception as e:
                    print(f"Warning: could not load {fpath}: {e}")
        self._recompute_stats()
        return loaded

    def _load_file(self, path: str) -> int:
        """Load a single JSON file and register its records."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Handle both single record and list of records
        if isinstance(data, list):
            records = data
        else:
            records = [data]

        count = 0
        for record in records:
            kind = record.get("kind", "")
            if kind == "hardware_run" or "hardware_run" in path:
                rec = HardwareRunRecord.from_dict(record)
                self.hardware_runs[rec.metadata.experiment_id] = rec
                count += 1
            elif kind == "sierpinski_experiment" or "sierpinski" in path:
                rec = SierpinskiExperimentRecord.from_dict(record)
                self.sierpinski_experiments[rec.experiment_id] = rec
                count += 1
            elif kind == "calibration_snapshot" or "calibration" in path:
                rec = CalibrationSnapshot.from_dict(record)
                self.calibrations[rec.snapshot_id] = rec
                count += 1
            else:
                # Auto-detect based on fields
                if "experiment_id" in record and "backend" in record:
                    rec = HardwareRunRecord.from_dict(record)
                    self.hardware_runs[rec.metadata.experiment_id] = rec
                    count += 1

        return count

    def save_directory(self, path: str) -> int:
        """Save all records to a directory as JSON files.

        Creates subdirectories: runs/, sierpinski/, calibrations/.

        Args:
            path: Root directory for saved records.

        Returns:
            Number of records saved.
        """
        os.makedirs(os.path.join(path, "runs"), exist_ok=True)
        os.makedirs(os.path.join(path, "sierpinski"), exist_ok=True)
        os.makedirs(os.path.join(path, "calibrations"), exist_ok=True)

        count = 0

        for rec in self.hardware_runs.values():
            fname = f"{rec.metadata.experiment_id}.json"
            fpath = os.path.join(path, "runs", fname)
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump({"kind": "hardware_run", **rec.to_dict()}, f, indent=2)
            count += 1

        for rec in self.sierpinski_experiments.values():
            fname = f"{rec.experiment_id}.json"
            fpath = os.path.join(path, "sierpinski", fname)
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump({"kind": "sierpinski_experiment", **rec.to_dict()}, f, indent=2)
            count += 1

        for rec in self.calibrations.values():
            fname = f"{rec.snapshot_id}.json"
            fpath = os.path.join(path, "calibrations", fname)
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump({"kind": "calibration_snapshot", **rec.to_dict()}, f, indent=2)
            count += 1

        return count

    # -------------------------------------------------------------------------
    # Query methods
    # -------------------------------------------------------------------------

    def find_runs(
        self,
        depth: Optional[int] = None,
        backend: Optional[str] = None,
        project: Optional[str] = None,
        hypothesis_tag: Optional[ExperimentTag] = None,
        circuit_family: Optional[CircuitFamily] = None,
        min_qubits: Optional[int] = None,
        max_qubits: Optional[int] = None,
        min_fidelity: Optional[float] = None,
        date_after: Optional[str] = None,
        date_before: Optional[str] = None,
    ) -> List[HardwareRunRecord]:
        """Find hardware runs matching filter criteria.

        All filter arguments are optional and combined with AND logic.

        Args:
            depth: Circuit depth must equal this value.
            backend: Backend name must match exactly.
            project: Project name must match exactly.
            hypothesis_tag: Hypothesis tag must match.
            circuit_family: Circuit family must match.
            min_qubits: Minimum qubit count.
            max_qubits: Maximum qubit count.
            min_fidelity: Minimum fidelity threshold.
            date_after: ISO-8601 date string — only runs after this date.
            date_before: ISO-8601 date string — only runs before this date.

        Returns:
            List of matching HardwareRunRecord, ordered by date descending.
        """
        results = []
        for rec in self.hardware_runs.values():
            if depth is not None and rec.depth != depth:
                continue
            if backend is not None and rec.backend != backend:
                continue
            if project is not None and rec.metadata.project != project:
                continue
            if hypothesis_tag is not None and rec.metadata.hypothesis_tag != hypothesis_tag:
                continue
            if circuit_family is not None and rec.metadata.circuit_family != circuit_family:
                continue
            if min_qubits is not None and rec.qubit_count < min_qubits:
                continue
            if max_qubits is not None and rec.qubit_count > max_qubits:
                continue
            if min_fidelity is not None and (
                rec.fidelity is None or rec.fidelity < min_fidelity
            ):
                continue
            if date_after is not None and rec.metadata.date < date_after:
                continue
            if date_before is not None and rec.metadata.date > date_before:
                continue
            results.append(rec)

        # Sort by date descending
        results.sort(key=lambda r: r.metadata.date, reverse=True)
        return results

    def find_sierpinski_experiments(
        self,
        recursion_level: Optional[int] = None,
        backend: Optional[str] = None,
        project: Optional[str] = None,
        route: Optional[str] = None,
        void_encoding_used: Optional[bool] = None,
        min_confidence: Optional[float] = None,
    ) -> List[SierpinskiExperimentRecord]:
        """Find Sierpinski experiments matching filter criteria."""
        results = []
        for rec in self.sierpinski_experiments.values():
            if recursion_level is not None and rec.recursion_level != recursion_level:
                continue
            if backend is not None and rec.hardware_record.backend != backend:
                continue
            if project is not None and rec.project != project:
                continue
            if route is not None and rec.route != route:
                continue
            if void_encoding_used is not None and rec.void_encoding_used != void_encoding_used:
                continue
            if min_confidence is not None and (
                rec.depth_invariant_confidence is None
                or rec.depth_invariant_confidence < min_confidence
            ):
                continue
            results.append(rec)
        results.sort(key=lambda r: r.hardware_record.metadata.date, reverse=True)
        return results

    def find_calibrations(
        self,
        backend: Optional[str] = None,
        date_after: Optional[str] = None,
        date_before: Optional[str] = None,
    ) -> List[CalibrationSnapshot]:
        """Find calibration snapshots matching filter criteria."""
        results = []
        for rec in self.calibrations.values():
            if backend is not None and rec.backend != backend:
                continue
            if date_after is not None and rec.timestamp < date_after:
                continue
            if date_before is not None and rec.timestamp > date_before:
                continue
            results.append(rec)
        results.sort(key=lambda r: r.timestamp, reverse=True)
        return results

    def get_run(self, experiment_id: str) -> Optional[HardwareRunRecord]:
        """Get a specific run by experiment ID."""
        return self.hardware_runs.get(experiment_id)

    def get_calibration(self, snapshot_id: str) -> Optional[CalibrationSnapshot]:
        """Get a specific calibration by snapshot ID."""
        return self.calibrations.get(snapshot_id)

    # -------------------------------------------------------------------------
    # Comparison: generated vs historical
    # -------------------------------------------------------------------------

    def compare_generated_to_history(
        self,
        graph_nodes: int,
        depth: int,
        backend: str,
        project: Optional[str] = None,
        tolerance: float = 0.1,
    ) -> Dict[str, Any]:
        """Compare a generated structure against historical hardware results.

        Finds hardware runs matching the given parameters and returns
        a comparison summary including fidelity, phi_deviation, and
        sierpinski_score if available.

        Args:
            graph_nodes: Number of nodes in the generated fractal graph.
            depth: Circuit depth or fractal recursion level.
            backend: Backend name to compare against.
            project: Optional project filter.
            tolerance: Fractional tolerance for graph node count matching.

        Returns:
            Dict with keys:
                - match_count: Number of matching historical runs
                - matches: List of matching HardwareRunRecord
                - avg_fidelity: Average fidelity of matches (or None)
                - avg_phi_deviation: Average phi_deviation of matches (or None)
                - avg_sierpinski_score: Average sierpinski_score (or None)
                - best_match: HardwareRunRecord with highest fidelity
                - node_tolerance: (1-tolerance)*graph_nodes to (1+tolerance)*graph_nodes
        """
        # Find matching runs
        candidates = self.find_runs(
            depth=depth,
            backend=backend,
            project=project,
        )

        # Filter by node count within tolerance
        node_low = graph_nodes * (1 - tolerance)
        node_high = graph_nodes * (1 + tolerance)
        matches = [
            r for r in candidates
            if node_low <= r.qubit_count <= node_high
        ]

        if not matches:
            return {
                "match_count": 0,
                "matches": [],
                "avg_fidelity": None,
                "avg_phi_deviation": None,
                "avg_sierpinski_score": None,
                "best_match": None,
                "node_tolerance": (node_low, node_high),
            }

        fidelities = [r.fidelity for r in matches if r.fidelity is not None]
        phi_devs = [r.phi_deviation for r in matches if r.phi_deviation is not None]
        scores = [r.sierpinski_score for r in matches if r.sierpinski_score is not None]

        best = max(matches, key=lambda r: r.fidelity or 0.0)

        return {
            "match_count": len(matches),
            "matches": matches,
            "avg_fidelity": sum(fidelities) / len(fidelities) if fidelities else None,
            "avg_phi_deviation": sum(phi_devs) / len(phi_devs) if phi_devs else None,
            "avg_sierpinski_score": sum(scores) / len(scores) if scores else None,
            "best_match": best,
            "node_tolerance": (node_low, node_high),
        }

    def compare_sierpinski_fixed_point(
        self,
        observed_value: float,
        expected_value: float = 0.6180339887,  # 1/φ
    ) -> Dict[str, float]:
        """Compare an observed fixed-point value against expected 1/φ.

        Args:
            observed_value: Observed fixed-point value.
            expected_value: Expected value (default 1/φ).

        Returns:
            Dict with absolute_error, relative_error, and within_tolerance flag.
        """
        abs_error = abs(observed_value - expected_value)
        rel_error = abs_error / expected_value
        return {
            "observed": observed_value,
            "expected": expected_value,
            "absolute_error": abs_error,
            "relative_error": rel_error,
            "within_1pct": abs_error < 0.01 * expected_value,
            "within_5pct": abs_error < 0.05 * expected_value,
        }

    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------

    def stats(self) -> CorpusStats:
        """Return current corpus statistics."""
        self._recompute_stats()
        return self._stats

    def _recompute_stats(self) -> None:
        """Recompute corpus statistics."""
        runs = list(self.hardware_runs.values())
        exps = list(self.sierpinski_experiments.values())
        cals = list(self.calibrations.values())

        projects = sorted(set(r.metadata.project for r in runs))
        backends = sorted(set(r.backend for r in runs))

        depths = [r.depth for r in runs if r.depth > 0]
        dates = [r.metadata.date for r in runs if r.metadata.date]

        self._stats = CorpusStats(
            total_runs=len(runs),
            total_sierpinski_experiments=len(exps),
            total_calibrations=len(cals),
            projects=projects,
            backends=backends,
            depth_range=(min(depths), max(depths)) if depths else (0, 0),
            date_range=(min(dates), max(dates)) if dates else ("", ""),
        )

    def __len__(self) -> int:
        return len(self.hardware_runs)


# -----------------------------------------------------------------------------
# Module-level convenience loaders
# -----------------------------------------------------------------------------

def load_project_corpus(
    project: str,
    base_path: Optional[str] = None
) -> ResearchCorpus:
    """Load a project corpus from the canonical imports directory.

    Args:
        project: One of "qsg", "sierpinski", "calibration".
        base_path: Base path to imports directory. Defaults to "./imports".

    Returns:
        ResearchCorpus populated with all records found.
    """
    if base_path is None:
        base_path = os.path.join(os.getcwd(), "imports")
    project_path = os.path.join(base_path, project)
    corpus = ResearchCorpus()
    if os.path.exists(project_path):
        corpus.load_directory(project_path)
    return corpus
