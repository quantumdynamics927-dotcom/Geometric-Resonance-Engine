#!/usr/bin/env python3
"""Seed the GRE research corpus from a source directory.

Scans a user-specified source directory, copies or converts selected artifacts
into ``imports/``, generates provenance sidecars, and validates schema
compliance.

Usage::

    python -m gre.research.seed_corpus \\
        --source ./prior_work/qsg_results \\
        --project qsg \\
        --dest ./imports/qsg \\
        --pattern "*.json" \\
        --sensitivity internal

    python -m gre.research.seed_corpus \\
        --source ./sierpinski_experiments \\
        --project sierpinski \\
        --dest ./imports/sierpinski \\
        --kind sierpinski_experiment
"""

import argparse
import json
import hashlib
import shutil
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from gre.research.catalog import discover_imports_dir
from gre.research import normalizers


# -----------------------------------------------------------------------------
# Schema validators
# -----------------------------------------------------------------------------

def validate_hardware_run(data: Dict[str, Any]) -> List[str]:
    """Validate a hardware run record. Returns list of error messages."""
    errors = []
    required = ["experiment_id", "backend", "depth"]
    for field in required:
        if field not in data or data[field] is None:
            errors.append(f"Missing required field: {field}")
    if "depth" in data:
        try:
            d = int(data["depth"])
            if d < 0:
                errors.append(f"depth must be non-negative, got {d}")
        except (ValueError, TypeError):
            errors.append(f"depth must be int-like, got {data['depth']}")
    return errors


def validate_sierpinski_experiment(data: Dict[str, Any]) -> List[str]:
    """Validate a Sierpinski experiment record. Returns list of error messages."""
    errors = []
    required = ["experiment_id", "recursion_level"]
    for field in required:
        if field not in data or data[field] is None:
            errors.append(f"Missing required field: {field}")
    return errors


def validate_calibration(data: Dict[str, Any]) -> List[str]:
    """Validate a calibration snapshot. Returns list of error messages."""
    errors = []
    if "snapshot_id" not in data or not data["snapshot_id"]:
        errors.append("Missing required field: snapshot_id")
    if "backend" not in data or not data["backend"]:
        errors.append("Missing required field: backend")
    return errors


VALIDATORS = {
    "hardware_run": validate_hardware_run,
    "sierpinski_experiment": validate_sierpinski_experiment,
    "calibration": validate_calibration,
}


def infer_kind(data: Dict[str, Any], source_path: Path) -> str:
    """Infer the artifact kind from data fields and path."""
    if "snapshot_id" in data:
        return "calibration"
    if "recursion_level" in data or "route" in data:
        return "sierpinski_experiment"
    if "experiment_id" in data or "backend" in data:
        return "hardware_run"
    # Fallback: check path
    path_lower = str(source_path).lower()
    if "sierpinski" in path_lower or "pascal" in path_lower:
        return "sierpinski_experiment"
    if "cal" in path_lower and "ibm" in path_lower:
        return "calibration"
    return "hardware_run"


def compute_hash(file_path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def now_iso() -> str:
    """Current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# -----------------------------------------------------------------------------
# Provenance generation
# -----------------------------------------------------------------------------

def generate_provenance(
    artifact_id: str,
    project: str,
    source_path: Path,
    sensitivity: str,
    kind: str,
    commit: str = "",
) -> Dict[str, Any]:
    """Generate a provenance sidecar dict for an imported artifact."""
    return {
        "artifact_id": artifact_id,
        "source_project": project,
        "source_artifact_id": artifact_id,
        "source_path": str(source_path),
        "source_commit": commit,
        "source_date": now_iso(),
        "import_date": now_iso(),
        "import_method": "seed_corpus",
        "sensitivity": sensitivity,
        "transform_chain": [
            {
                "step_id": 0,
                "transform_type": "ingest",
                "description": f"{source_path.suffix} file ingested via seed_corpus",
                "parameters": {"kind": kind},
            }
        ],
        "claims_supported": [],
        "linked_files": [],
        "notes": f"Imported from {source_path}",
    }


def generate_summary(
    data: Dict[str, Any],
    artifact_id: str,
    project: str,
    kind: str,
) -> str:
    """Generate a summary Markdown file from a data dict."""
    lines = [
        f"# {artifact_id}",
        "",
        f"**Project**: {project}",
        f"**Kind**: {kind}",
        f"**Imported**: {now_iso()}",
        "",
    ]

    if "backend" in data:
        lines.append(f"**Backend**: {data['backend']}")
    if "date" in data:
        lines.append(f"**Date**: {data['date']}")
    if "depth" in data:
        lines.append(f"**Depth**: {data['depth']}")
    if "recursion_level" in data:
        lines.append(f"**Level**: {data['recursion_level']}")
    if "route" in data:
        lines.append(f"**Route**: {data['route']}")
    if "fidelity" in data:
        lines.append(f"**Fidelity**: {data['fidelity']}")
    if "phi_deviation" in data:
        lines.append(f"**φ Deviation**: {data['phi_deviation']}")

    lines.extend(["", "## Notes", "", "Imported via seed_corpus utility."])
    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Core seeding logic
# -----------------------------------------------------------------------------

def seed_from_directory(
    source_dir: Path,
    dest_dir: Path,
    project: str,
    kind_hint: str = "",
    pattern: str = "*",
    sensitivity: str = "internal",
    commit: str = "",
    copy_files: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Seed artifacts from a source directory into the corpus.

    Args:
        source_dir: Source directory to scan.
        dest_dir: Destination directory (created if needed).
        project: Project name (e.g., "qsg", "sierpinski").
        kind_hint: Override kind ("hardware_run", "sierpinski_experiment", "calibration").
        pattern: Glob pattern for files to import.
        sensitivity: Sensitivity level.
        commit: Source git commit hash.
        copy_files: If True, copy files to dest_dir; if False, only generate sidecars.
        dry_run: If True, don't write anything.

    Returns:
        Dict with import statistics.
    """
    results = {
        "total": 0,
        "imported": 0,
        "skipped": 0,
        "errors": 0,
        "artifacts": [],
    }

    if not source_dir.is_dir():
        print(f"ERROR: Source directory not found: {source_dir}")
        results["errors"] += 1
        return results

    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)

    source_files = sorted(source_dir.glob(pattern))
    if not source_files:
        print(f"WARNING: No files matching '{pattern}' in {source_dir}")
        # Also try without recursive globbing
        source_files = list(source_dir.iterdir())
        source_files = [f for f in source_files if f.is_file() and f.match(pattern)]

    for file_path in source_files:
        if file_path.is_dir():
            continue
        results["total"] += 1

        try:
            # Load file
            if file_path.suffix == ".json":
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)
            elif file_path.suffix == ".csv":
                import csv
                rows = []
                with open(file_path, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                if not rows:
                    print(f"  SKIP (empty CSV): {file_path.name}")
                    results["skipped"] += 1
                    continue
                # Merge all rows as a list under "rows" key
                data = {"rows": rows}
            else:
                print(f"  SKIP (unsupported type): {file_path.name}")
                results["skipped"] += 1
                continue

            # Infer artifact ID
            artifact_id = (
                data.get("experiment_id")
                or data.get("snapshot_id")
                or data.get("artifact_id")
                or file_path.stem
            )
            artifact_id = str(artifact_id)

            # Infer kind
            kind = kind_hint or infer_kind(data, file_path)

            # Validate
            validator = VALIDATORS.get(kind)
            if validator:
                errors = validator(data)
                if errors:
                    print(f"  VALIDATION ERRORS for {artifact_id}:")
                    for err in errors:
                        print(f"    - {err}")

            # Validate data
            result = normalizers.auto_normalize(data, source_project=project)
            if result.warnings:
                for w in result.warnings:
                    print(f"  WARNING [{artifact_id}]: {w.field}: {w.message}")

            # Generate provenance
            provenance = generate_provenance(
                artifact_id=artifact_id,
                project=project,
                source_path=file_path,
                sensitivity=sensitivity,
                kind=kind,
                commit=commit,
            )

            # Generate summary
            summary = generate_summary(data, artifact_id, project, kind)

            # Write output
            if not dry_run:
                dest_file = dest_dir / f"{artifact_id}{file_path.suffix}"

                if copy_files:
                    shutil.copy2(file_path, dest_file)

                prov_path = dest_dir / f"{artifact_id}.provenance.json"
                with open(prov_path, "w", encoding="utf-8") as f:
                    json.dump(provenance, f, indent=2)

                summary_path = dest_dir / f"{artifact_id}.summary.md"
                with open(summary_path, "w", encoding="utf-8") as f:
                    f.write(summary)

            print(f"  {'[DRY RUN] ' if dry_run else ''}Imported: {artifact_id} ({kind})")
            results["imported"] += 1
            results["artifacts"].append({
                "artifact_id": artifact_id,
                "kind": kind,
                "source": str(file_path),
                "dest": str(dest_dir / f"{artifact_id}{file_path.suffix}") if not dry_run else None,
            })

        except Exception as exc:
            print(f"  ERROR importing {file_path.name}: {exc}")
            results["errors"] += 1

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Seed the GRE research corpus from a source directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:

  # Import all JSON files from a QSG results directory
  python -m gre.research.seed_corpus \\
      --source ./prior_work/qsg_results \\
      --project qsg \\
      --dest ./imports/qsg \\
      --pattern "*.json"

  # Import Sierpinski experiments
  python -m gre.research.seed_corpus \\
      --source ./sierpinski_experiments \\
      --project sierpinski \\
      --dest ./imports/sierpinski \\
      --kind sierpinski_experiment

  # Dry run to preview what would be imported
  python -m gre.research.seed_corpus \\
      --source ./my_data \\
      --project test \\
      --dest /tmp/test_imports \\
      --dry-run
""",
    )
    parser.add_argument(
        "--source", "-s",
        type=Path,
        required=True,
        help="Source directory containing artifacts to import",
    )
    parser.add_argument(
        "--dest", "-d",
        type=Path,
        required=True,
        help="Destination directory within imports/",
    )
    parser.add_argument(
        "--project", "-p",
        required=True,
        help="Project name (e.g., qsg, sierpinski, calibration)",
    )
    parser.add_argument(
        "--kind", "-k",
        choices=["hardware_run", "sierpinski_experiment", "calibration", ""],
        default="",
        help="Override artifact kind (auto-detected if not specified)",
    )
    parser.add_argument(
        "--pattern", "-t",
        default="*",
        help="Glob pattern for files to import (default: *)",
    )
    parser.add_argument(
        "--sensitivity",
        default="internal",
        choices=["open", "internal", "restricted", "confidential"],
        help="Sensitivity level for imported artifacts",
    )
    parser.add_argument(
        "--commit", "-c",
        default="",
        help="Source git commit hash",
    )
    parser.add_argument(
        "--no-copy",
        action="store_true",
        help="Generate sidecars only (don't copy source files)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be imported without writing files",
    )
    parser.add_argument(
        "--imports-root",
        type=Path,
        default=Path(__file__).parent.parent.parent / "imports",
        help="Root imports directory (default: <gre>/imports)",
    )

    args = parser.parse_args()

    # Resolve dest relative to imports-root
    if not args.dest.is_absolute():
        dest_dir = args.imports_root / args.dest
    else:
        dest_dir = args.dest

    print(f"\n=== GRE Corpus Seeder ===")
    print(f"  Source:    {args.source}")
    print(f"  Dest:      {dest_dir}")
    print(f"  Project:   {args.project}")
    print(f"  Kind:      {args.kind or 'auto-detect'}")
    print(f"  Pattern:   {args.pattern}")
    print(f"  Sensitivity: {args.sensitivity}")
    print(f"  Mode:      {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    results = seed_from_directory(
        source_dir=args.source,
        dest_dir=dest_dir,
        project=args.project,
        kind_hint=args.kind,
        pattern=args.pattern,
        sensitivity=args.sensitivity,
        commit=args.commit,
        copy_files=not args.no_copy,
        dry_run=args.dry_run,
    )

    print()
    print(f"=== Results ===")
    print(f"  Total:    {results['total']}")
    print(f"  Imported: {results['imported']}")
    print(f"  Skipped:  {results['skipped']}")
    print(f"  Errors:   {results['errors']}")

    return 0 if results["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
