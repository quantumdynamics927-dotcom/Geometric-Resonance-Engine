"""Import utilities for CSV, JSON, and Markdown-derived metadata.

These functions ingest prior research from QSG, Sierpinski, and other
projects into the GRE corpus, with automatic provenance tracking.

Each import function:
1. Reads raw files from the source project directory
2. Normalizes the data into GRE schemas
3. Assigns provenance metadata (source_project, path, commit, sensitivity)
4. Returns a list of records and their provenance sidecars
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
import csv
import json
import os
import re
from pathlib import Path

from .schemas import (
    HardwareRunRecord,
    SierpinskiExperimentRecord,
    CalibrationSnapshot,
    ExperimentMetadata,
    ExperimentTag,
    CircuitFamily,
    ArtifactDescriptor,
)
from .provenance import ProvenanceSidecar, TransformStep


# -----------------------------------------------------------------------------
# Import result containers
# -----------------------------------------------------------------------------

@dataclass
class ImportResult:
    """Result of an import operation."""
    records_imported: int
    records_failed: int
    records: List[Any]  # HardwareRunRecord or SierpinskiExperimentRecord
    failures: List[Dict[str, str]]  # {file, error} pairs
    provenance_added: List[ProvenanceSidecar]


# -----------------------------------------------------------------------------
# CSV importers
# -----------------------------------------------------------------------------

def import_hardware_runs_from_csv(
    csv_path: str,
    source_project: str,
    source_commit: str = "",
    sensitivity: str = "internal",
    backend_col: str = "backend",
    depth_col: str = "depth",
    qubits_col: str = "qubit_count",
    shots_col: str = "shots",
    experiment_id_col: str = "experiment_id",
    date_col: str = "date",
    notes_col: str = "notes",
    delimiter: str = ",",
    custom_mappers: Optional[Dict[str, Callable[[str], Any]]] = None,
) -> ImportResult:
    """Import hardware runs from a CSV file.

    Args:
        csv_path: Path to the CSV file.
        source_project: Name of the source project (e.g., "qsg").
        source_commit: Git commit hash at time of export.
        sensitivity: "public", "internal", or "restricted".
        *_col: Column name mappings from CSV header to record field.
        delimiter: CSV delimiter (default ",").
        custom_mappers: Optional dict of column_name → parsing_function for
            non-standard columns.

    Returns:
        ImportResult with imported records and provenance information.
    """
    custom_mappers = custom_mappers or {}
    records = []
    failures = []
    provenance_added = []

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row_num, row in enumerate(reader):
            try:
                experiment_id = row.get(experiment_id_col, f"{source_project}-import-{row_num}")
                backend = row.get(backend_col, "unknown")
                depth = int(row.get(depth_col, 0))
                qubit_count = int(row.get(qubits_col, 0))
                shots = int(row.get(shots_col, 0))
                date = row.get(date_col, datetime.utcnow().isoformat() + "Z")
                notes = row.get(notes_col, "")

                # Parse optional metric columns
                observed_metrics: Dict[str, float] = {}
                for key, val in row.items():
                    key_lower = key.lower()
                    if key_lower.startswith("metric_") and val:
                        metric_name = key_lower[len("metric_"):]
                        try:
                            observed_metrics[metric_name] = float(val)
                        except ValueError:
                            pass
                    elif key_lower in ("fidelity", "phi_deviation", "sierpinski_score") and val:
                        try:
                            observed_metrics[key_lower] = float(val)
                        except ValueError:
                            pass

                # Apply custom mappers
                for col_name, mapper_fn in custom_mappers.items():
                    if col_name in row:
                        row[col_name] = mapper_fn(row[col_name])

                # Determine hypothesis tag from notes or experiment_id
                hypothesis_tag = _infer_hypothesis_tag(notes, experiment_id)

                meta = ExperimentMetadata(
                    experiment_id=experiment_id,
                    project=source_project,
                    date=date,
                    hypothesis_tag=hypothesis_tag,
                    circuit_family=CircuitFamily.FRACTAL_WALK,
                    notes=notes,
                )

                provenance = ProvenanceSidecar(
                    source_project=source_project,
                    source_artifact_id=experiment_id,
                    source_path=csv_path,
                    source_commit=source_commit,
                    source_date=date,
                    backend=backend,
                    import_method="csv_import",
                    sensitivity=sensitivity,
                    transform_chain=[
                        TransformStep(
                            step_id=0,
                            transform_type="normalize",
                            description=f"CSV row {row_num} → HardwareRunRecord",
                            parameters={"csv_path": csv_path, "row": row_num},
                            tool="gre.research.ingest.import_hardware_runs_from_csv",
                        )
                    ],
                )

                fidelity = observed_metrics.get("fidelity")
                phi_deviation = observed_metrics.get("phi_deviation")
                sierpinski_score = observed_metrics.get("sierpinski_score")

                record = HardwareRunRecord(
                    metadata=meta,
                    backend=backend,
                    qubit_count=qubit_count,
                    depth=depth,
                    shots=shots,
                    observed_metrics=observed_metrics,
                    fidelity=fidelity,
                    phi_deviation=phi_deviation,
                    sierpinski_score=sierpinski_score,
                    provenance=provenance,
                )

                records.append(record)
                provenance_added.append(provenance)

            except Exception as e:
                failures.append({
                    "file": csv_path,
                    "row": row_num,
                    "error": str(e),
                    "row_data": str(row)[:200],
                })

    return ImportResult(
        records_imported=len(records),
        records_failed=len(failures),
        records=records,
        failures=failures,
        provenance_added=provenance_added,
    )


def import_sierpinski_experiments_from_csv(
    csv_path: str,
    source_project: str,
    source_commit: str = "",
    sensitivity: str = "internal",
    **kwargs
) -> ImportResult:
    """Import Sierpinski experiments from a CSV file.

    Extends import_hardware_runs_from_csv with Sierpinski-specific fields:
    recursion_level, hausdorff_dimension, depth_invariant_fixed_point,
    depth_invariant_confidence, route, void_encoding_used.

    Args:
        csv_path: Path to the CSV file.
        source_project: Name of the source project.
        source_commit: Git commit hash.
        sensitivity: "public", "internal", or "restricted".
        **kwargs: Passed to import_hardware_runs_from_csv.

    Returns:
        ImportResult with SierpinskiExperimentRecord instances.
    """
    base_result = import_hardware_runs_from_csv(
        csv_path=csv_path,
        source_project=source_project,
        source_commit=source_commit,
        sensitivity=sensitivity,
        **kwargs,
    )

    sier_records = []
    for hw_record in base_result.records:
        # Try to extract Sierpinski-specific fields from notes or metadata
        hw_dict = hw_record.to_dict()
        notes = hw_record.metadata.notes

        recursion_level = _extract_int(notes, r"level\s*[=:]\s*(\d+)", None)
        fixed_point = _extract_float(notes, r"(?:fixed.?point|1?/?.?phi)\s*[=:]\s*([\d.]+)", None)
        confidence = _extract_float(notes, r"confidence\s*[=:]\s*([\d.]+)", None)
        route = _extract_str(notes, r"route\s*[=:]\s*(\w+)", "ifs")
        void_used = "void" in notes.lower()

        sier = SierpinskiExperimentRecord(
            hardware_record=hw_record,
            recursion_level=recursion_level or hw_record.depth,
            depth_invariant_fixed_point=fixed_point,
            depth_invariant_confidence=confidence,
            route=route or "ifs",
            void_encoding_used=void_used,
            fractal_graph_nodes=hw_record.qubit_count,
            fractal_graph_edges=hw_record.depth,
        )
        sier_records.append(sier)

    return ImportResult(
        records_imported=len(sier_records),
        records_failed=base_result.records_failed,
        records=sier_records,
        failures=base_result.failures,
        provenance_added=base_result.provenance_added,
    )


# -----------------------------------------------------------------------------
# JSON importers
# -----------------------------------------------------------------------------

def import_from_json(
    json_path: str,
    source_project: str,
    source_commit: str = "",
    sensitivity: str = "internal",
    record_kind: str = "hardware_run",  # "hardware_run", "sierpinski_experiment", "calibration"
) -> ImportResult:
    """Import records from a JSON file.

    JSON can contain a single record or a list of records.

    Args:
        json_path: Path to the JSON file.
        source_project: Name of the source project.
        source_commit: Git commit hash.
        sensitivity: "public", "internal", or "restricted".
        record_kind: "hardware_run", "sierpinski_experiment", or "calibration".

    Returns:
        ImportResult with imported records.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        data = [data]

    records = []
    failures = []
    provenance_added = []

    for i, item in enumerate(data):
        try:
            # Add provenance sidecar if not present
            if "provenance" not in item:
                item["provenance"] = {
                    "source_project": source_project,
                    "source_artifact_id": item.get("experiment_id", f"{source_project}-json-{i}"),
                    "source_path": json_path,
                    "source_commit": source_commit,
                    "import_method": "json_import",
                    "sensitivity": sensitivity,
                }

            if record_kind == "hardware_run":
                record = HardwareRunRecord.from_dict(item)
            elif record_kind == "sierpinski_experiment":
                record = SierpinskiExperimentRecord.from_dict(item)
            elif record_kind == "calibration":
                record = CalibrationSnapshot.from_dict(item)
            else:
                raise ValueError(f"Unknown record_kind: {record_kind}")

            records.append(record)
            provenance_added.append(record.provenance if hasattr(record, "provenance") else ProvenanceSidecar())

        except Exception as e:
            failures.append({
                "file": json_path,
                "index": i,
                "error": str(e),
            })

    return ImportResult(
        records_imported=len(records),
        records_failed=len(failures),
        records=records,
        failures=failures,
        provenance_added=provenance_added,
    )


# -----------------------------------------------------------------------------
# Markdown summary importers
# -----------------------------------------------------------------------------

def import_sierpinski_summary_from_markdown(
    md_path: str,
    source_project: str,
    source_commit: str = "",
    sensitivity: str = "internal",
) -> SierpinskiExperimentRecord:
    """Import a Sierpinski experiment summary from a Markdown file.

    Parses structured Markdown to extract claims, metrics, and metadata,
    then creates a SierpinskiExperimentRecord with provenance.

    Expected Markdown format:
    ---
    experiment_id: qsg-sierpinski-001
    date: 2024-03-15
    backend: ibmq_qasm_simulator
    recursion_level: 5
    route: ifs
    ---
    ## Claims
    ## Metrics
    ## Notes

    Args:
        md_path: Path to the Markdown file.
        source_project: Name of the source project.
        source_commit: Git commit hash.
        sensitivity: "public", "internal", or "restricted".

    Returns:
        SierpinskiExperimentRecord parsed from the Markdown.
    """
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Parse frontmatter (YAML between --- markers)
    frontmatter = {}
    if content.startswith("---"):
        parts = content[3:].split("---", 1)
        if len(parts) == 2:
            fm_text, body = parts
            import yaml
            try:
                frontmatter = yaml.safe_load(fm_text) or {}
            except Exception:
                pass

    experiment_id = frontmatter.get("experiment_id", os.path.basename(md_path))
    date = frontmatter.get("date", datetime.utcnow().isoformat() + "Z")
    backend = frontmatter.get("backend", "unknown")
    recursion_level = int(frontmatter.get("recursion_level", 0))
    route = frontmatter.get("route", "ifs")

    # Extract claims from ## Claims section
    claims = _extract_section(content, "Claims")
    notes = _extract_section(content, "Notes")
    metrics_text = _extract_section(content, "Metrics")

    # Parse metrics from text
    observed_metrics = {}
    for match in re.finditer(r"([\w_]+)\s*[=:]\s*([\d.]+)", metrics_text):
        key, val = match.groups()
        try:
            observed_metrics[key.strip()] = float(val)
        except ValueError:
            pass

    fidelity = observed_metrics.get("fidelity")
    fixed_point = observed_metrics.get("fixed_point") or observed_metrics.get("1/phi")
    confidence = observed_metrics.get("confidence")

    hypothesis_tag = _infer_hypothesis_tag(notes, experiment_id)

    meta = ExperimentMetadata(
        experiment_id=experiment_id,
        project=source_project,
        date=date,
        hypothesis_tag=hypothesis_tag,
        circuit_family=CircuitFamily.FRACTAL_WALK,
        notes=notes,
    )

    provenance = ProvenanceSidecar(
        source_project=source_project,
        source_artifact_id=experiment_id,
        source_path=md_path,
        source_commit=source_commit,
        source_date=date,
        backend=backend,
        import_method="markdown_import",
        sensitivity=sensitivity,
        claims_supported=claims.split("\n"),
        transform_chain=[
            TransformStep(
                step_id=0,
                transform_type="parse",
                description="Markdown frontmatter + section parsing",
                parameters={"md_path": md_path},
                tool="gre.research.ingest.import_sierpinski_summary_from_markdown",
            )
        ],
    )

    hw_record = HardwareRunRecord(
        metadata=meta,
        backend=backend,
        qubit_count=0,  # Unknown from Markdown
        depth=recursion_level,
        shots=0,
        observed_metrics=observed_metrics,
        fidelity=fidelity,
        provenance=provenance,
    )

    return SierpinskiExperimentRecord(
        hardware_record=hw_record,
        recursion_level=recursion_level,
        depth_invariant_fixed_point=fixed_point,
        depth_invariant_confidence=confidence,
        route=route,
        void_encoding_used="void" in notes.lower(),
    )


# -----------------------------------------------------------------------------
# Batch import from directory
# -----------------------------------------------------------------------------

def import_project_directory(
    source_dir: str,
    source_project: str,
    source_commit: str = "",
    sensitivity: str = "internal",
    file_patterns: Optional[Dict[str, str]] = None,
) -> Dict[str, ImportResult]:
    """Import all supported files from a source project directory.

    Recursively scans source_dir and dispatches each file to the
    appropriate importer based on extension.

    Supported:
        *.csv → import_hardware_runs_from_csv
        *.json → import_from_json
        *.md / *.markdown → import_sierpinski_summary_from_markdown

    Args:
        source_dir: Root directory of the source project.
        source_project: Name of the source project.
        source_commit: Git commit hash at export time.
        sensitivity: "public", "internal", or "restricted".
        file_patterns: Optional override of pattern → importer function.

    Returns:
        Dict mapping file type → ImportResult.
    """
    if file_patterns is None:
        file_patterns = {
            "*.csv": "hardware_run",
            "*.json": "hardware_run",
            "*.md": "sierpinski_experiment",
        }

    results: Dict[str, ImportResult] = {}
    for root, _, files in os.walk(source_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            ext = os.path.splitext(fname)[1].lower()

            if ext == ".csv":
                result = import_hardware_runs_from_csv(
                    fpath, source_project, source_commit, sensitivity
                )
                results[fpath] = result
            elif ext == ".json":
                result = import_from_json(
                    fpath, source_project, source_commit, sensitivity
                )
                results[fpath] = result
            elif ext in (".md", ".markdown"):
                try:
                    sier = import_sierpinski_summary_from_markdown(
                        fpath, source_project, source_commit, sensitivity
                    )
                    results[fpath] = ImportResult(
                        records_imported=1,
                        records_failed=0,
                        records=[sier],
                        failures=[],
                        provenance_added=[sier.hardware_record.provenance],
                    )
                except Exception as e:
                    results[fpath] = ImportResult(
                        records_imported=0,
                        records_failed=1,
                        records=[],
                        failures=[{"file": fpath, "error": str(e)}],
                        provenance_added=[],
                    )

    return results


# -----------------------------------------------------------------------------
# Helper utilities
# -----------------------------------------------------------------------------

def _infer_hypothesis_tag(notes: str, experiment_id: str) -> ExperimentTag:
    """Infer the hypothesis tag from notes and experiment_id text."""
    text = (notes + " " + experiment_id).lower()
    if "depth_invariant" in text or "fixed_point" in text or "1/phi" in text:
        return ExperimentTag.FIXED_POINT_1_OVER_PHI
    elif "structural_encoding" in text:
        return ExperimentTag.STRUCTURAL_ENCODING
    elif "qutrit" in text:
        return ExperimentTag.QUATRIT_MAPPING
    elif "entropy" in text:
        return ExperimentTag.ENTROPY_EXTRACTION
    elif "decoherence" in text or "void" in text:
        return ExperimentTag.DECOHERENCE_FREE_SUBSPACE
    elif "state_transfer" in text or "walk" in text:
        return ExperimentTag.GRAPH_STATE_TRANSFER
    elif "multiband" in text or "resonance" in text:
        return ExperimentTag.MULTIBAND_RESONANCE
    elif "ising" in text or "critical" in text:
        return ExperimentTag.QUANTUM_ISING_CRITICAL
    else:
        return ExperimentTag.OTHER


def _extract_section(content: str, section_name: str) -> str:
    """Extract a Markdown section by name."""
    pattern = rf"##\s+{section_name}\s*\n(.*?)(?=\n##|\Z)"
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _extract_float(text: str, pattern: str, default: Any) -> Any:
    """Extract a float from text using a regex pattern."""
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return default


def _extract_int(text: str, pattern: str, default: Any) -> Any:
    """Extract an integer from text using a regex pattern."""
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return default


def _extract_str(text: str, pattern: str, default: str) -> str:
    """Extract a string from text using a regex pattern."""
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else default
