#!/usr/bin/env python3
"""Print a diagnostic report on the GRE research corpus.

Analyzes the imports/ directory and reports:
- Projects ingested and their artifact counts
- Backends represented across all projects
- Run counts by type (hardware_run, sierpinski_experiment, calibration)
- Artifacts with missing provenance sidecars
- Artifacts with missing provenance data (no source_commit, no transform_chain)
- Artifacts with missing metrics (no fidelity, no phi_deviation)
- Duplicate artifact IDs (same ID in multiple projects)

Usage::

    python -m gre.research.corpus_report
    python -m gre.research.corpus_report --imports ./imports
    python -m gre.research.corpus_report --verbose
"""

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Set

sys.path.insert(0, str(Path(__file__).parent.parent))

from gre.research.catalog import discover_imports_dir, CorpusCatalog


# -----------------------------------------------------------------------------
# Diagnostics
# -----------------------------------------------------------------------------

def check_missing_provenance(catalog: CorpusCatalog) -> List[Dict[str, Any]]:
    """Find catalog entries without provenance sidecar files."""
    missing = []
    for entry in catalog.entries:
        if not entry.provenance_path:
            missing.append({
                "artifact_id": entry.artifact_id,
                "artifact_type": entry.artifact_type,
                "source_project": entry.source_project,
                "data_path": entry.data_path,
            })
    return missing


def check_provenance_completeness(catalog: CorpusCatalog) -> List[Dict[str, Any]]:
    """Check provenance sidecars for missing fields."""
    issues = []
    for entry in catalog.entries:
        if not entry.provenance_path:
            continue
        try:
            with open(entry.provenance_path, encoding="utf-8") as f:
                prov = json.load(f)

            missing = []
            if not prov.get("source_commit"):
                missing.append("source_commit")
            if not prov.get("source_date"):
                missing.append("source_date")
            if not prov.get("transform_chain"):
                missing.append("transform_chain")
            if not prov.get("import_method"):
                missing.append("import_method")

            if missing:
                issues.append({
                    "artifact_id": entry.artifact_id,
                    "source_project": entry.source_project,
                    "missing_fields": missing,
                })
        except (json.JSONDecodeError, IOError) as exc:
            issues.append({
                "artifact_id": entry.artifact_id,
                "source_project": entry.source_project,
                "error": str(exc),
            })
    return issues


def check_missing_metrics(catalog: CorpusCatalog) -> List[Dict[str, Any]]:
    """Find artifacts with no fidelity, phi_deviation, or sierpinski_score."""
    missing = []
    for entry in catalog.entries:
        if entry.artifact_type == "calibration":
            continue  # Calibrations don't need fidelity
        if not entry.data_path:
            continue
        data_path = Path(entry.data_path)
        if data_path.suffix != ".json":
            continue
        try:
            with open(data_path, encoding="utf-8") as f:
                data = json.load(f)
            has_fidelity = "fidelity" in data and data["fidelity"] is not None
            has_phi = "phi_deviation" in data and data["phi_deviation"] is not None
            has_score = "sierpinski_score" in data and data["sierpinski_score"] is not None
            has_fixed_point = (
                "depth_invariant_fixed_point" in data
                and data["depth_invariant_fixed_point"] is not None
            )
            if not (has_fidelity or has_phi or has_score or has_fixed_point):
                missing.append({
                    "artifact_id": entry.artifact_id,
                    "artifact_type": entry.artifact_type,
                    "source_project": entry.source_project,
                    "data_path": entry.data_path,
                })
        except (json.JSONDecodeError, IOError):
            pass
    return missing


def check_duplicate_ids(catalog: CorpusCatalog) -> List[Dict[str, Any]]:
    """Find duplicate artifact IDs across projects."""
    id_to_projects: Dict[str, Set[str]] = defaultdict(set)
    for entry in catalog.entries:
        id_to_projects[entry.artifact_id].add(entry.source_project)

    duplicates = []
    for aid, projects in sorted(id_to_projects.items()):
        if len(projects) > 1:
            duplicates.append({
                "artifact_id": aid,
                "projects": sorted(projects),
            })
    return duplicates


def check_unlinked_sidecars(imports_dir: Path) -> List[Dict[str, Any]]:
    """Find provenance sidecar files with no corresponding data file."""
    unlinked = []
    if not imports_dir.is_dir():
        return unlinked

    for project_dir in imports_dir.iterdir():
        if not project_dir.is_dir() or project_dir.name.startswith("_"):
            continue
        for prov_file in project_dir.glob("*.provenance.json"):
            stem = prov_file.stem  # e.g. "sierpinski-level5-ifs"
            # Look for a corresponding data file
            data_file = project_dir / f"{stem}.json"
            if not data_file.exists():
                unlinked.append({
                    "provenance_file": str(prov_file.relative_to(imports_dir)),
                    "artifact_id": stem,
                    "project": project_dir.name,
                })
    return unlinked


# -----------------------------------------------------------------------------
# Evidence class / validation tier / generation diagnostics
# -----------------------------------------------------------------------------


def check_by_evidence_class(catalog: CorpusCatalog) -> Dict[str, int]:
    """Count artifacts by evidence class (hardware runs only, not calibrations)."""
    counts: Dict[str, int] = defaultdict(int)
    for entry in catalog.entries:
        if entry.artifact_type == "calibration":
            continue
        if not entry.data_path:
            continue
        data_path = Path(entry.data_path)
        if data_path.suffix != ".json":
            continue
        try:
            with open(data_path, encoding="utf-8") as f:
                data = json.load(f)
            ec = data.get("evidence_class", "unknown")
            counts[ec] += 1
        except (json.JSONDecodeError, IOError):
            counts["unknown"] += 1
    return dict(counts)


def check_by_validation_tier(catalog: CorpusCatalog) -> Dict[str, int]:
    """Count artifacts by validation tier (hardware runs only, not calibrations)."""
    counts: Dict[str, int] = defaultdict(int)
    for entry in catalog.entries:
        if entry.artifact_type == "calibration":
            continue
        if not entry.data_path:
            continue
        data_path = Path(entry.data_path)
        if data_path.suffix != ".json":
            continue
        try:
            with open(data_path, encoding="utf-8") as f:
                data = json.load(f)
            vt = data.get("validation_tier", "unknown")
            counts[vt] += 1
        except (json.JSONDecodeError, IOError):
            counts["unknown"] += 1
    return dict(counts)


def check_by_backend_generation(catalog: CorpusCatalog) -> Dict[str, int]:
    """Count artifacts by backend generation (hardware runs only, not calibrations)."""
    counts: Dict[str, int] = defaultdict(int)
    for entry in catalog.entries:
        if entry.artifact_type == "calibration":
            continue
        if not entry.data_path:
            continue
        data_path = Path(entry.data_path)
        if data_path.suffix != ".json":
            continue
        try:
            with open(data_path, encoding="utf-8") as f:
                data = json.load(f)
            bg = data.get("backend_generation", "unknown")
            counts[bg] += 1
        except (json.JSONDecodeError, IOError):
            counts["unknown"] += 1
    return dict(counts)


def check_missing_physical_calibration(catalog: CorpusCatalog) -> List[Dict[str, Any]]:
    """Find hardware runs that lack physical calibration context.

    A hardware run needs either a linked calibration snapshot with
    calibration_completeness=physical, or the backend_generation must be
    'simulator'.
    """
    issues = []
    for entry in catalog.entries:
        if entry.artifact_type == "calibration":
            continue
        if not entry.data_path:
            continue
        data_path = Path(entry.data_path)
        if data_path.suffix != ".json":
            continue
        try:
            with open(data_path, encoding="utf-8") as f:
                data = json.load(f)

            backend_gen = data.get("backend_generation", "unknown")
            # Simulators don't need physical calibration
            if backend_gen == "simulator":
                continue

            cal_id = data.get("calibration_snapshot_id")
            if not cal_id:
                # Check if calibration exists in the corpus
                cal_found = False
                for e in catalog.entries:
                    if e.artifact_type == "calibration" and e.artifact_id == cal_id:
                        cal_path = Path(e.data_path)
                        if cal_path.exists():
                            with open(cal_path, encoding="utf-8") as cf:
                                cal_data = json.load(cf)
                            if cal_data.get("calibration_completeness") == "physical":
                                cal_found = True
                        break
                if not cal_found:
                    issues.append({
                        "artifact_id": entry.artifact_id,
                        "source_project": entry.source_project,
                        "backend": data.get("backend", "unknown"),
                        "backend_generation": backend_gen,
                        "calibration_snapshot_id": cal_id or "(none)",
                        "reason": "no physical calibration snapshot linked",
                    })
        except (json.JSONDecodeError, IOError):
            pass
    return issues


# -----------------------------------------------------------------------------
# Reporting
# -----------------------------------------------------------------------------

def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_sub(title: str) -> None:
    print(f"\n## {title}")


def report_summary(catalog: CorpusCatalog, imports_dir: Path) -> None:
    """Print overall corpus summary."""
    print_section("Corpus Summary")

    stats = catalog.stats()
    print(f"  Total artifacts:     {stats['total_artifacts']}")
    print(f"  Unique claims:        {stats['unique_claims']}")
    print(f"  Projects:             {', '.join(sorted(catalog.projects()))}")

    print_sub("By Type")
    for k, v in sorted(stats["by_type"].items()):
        print(f"    {k:<30} {v}")
    if not stats["by_type"]:
        print("    (none)")

    print_sub("By Project")
    for k, v in sorted(stats["by_project"].items()):
        print(f"    {k:<30} {v}")
    if not stats["by_project"]:
        print("    (none)")

    print_sub("By Backend")
    for k, v in sorted(stats["by_backend"].items()):
        print(f"    {k:<30} {v}")
    if not stats["by_backend"]:
        print("    (none)")

    print_sub("By Sensitivity")
    sensitivities = defaultdict(int)
    for e in catalog.entries:
        sensitivities[e.sensitivity] += 1
    for k, v in sorted(sensitivities.items()):
        print(f"    {k:<30} {v}")
    if not sensitivities:
        print("    (none)")


def report_missing_provenance(catalog: CorpusCatalog) -> None:
    """Report artifacts without provenance sidecars."""
    print_section("Missing Provenance Sidecars")
    missing = check_missing_provenance(catalog)
    if not missing:
        print("  All artifacts have provenance sidecars [OK]")
        return
    print(f"  {len(missing)} artifact(s) missing provenance sidecar:")
    for item in missing:
        print(f"    [{item['source_project']}] {item['artifact_id']} ({item['artifact_type']})")


def report_provenance_completeness(catalog: CorpusCatalog) -> None:
    """Report provenance sidecars with incomplete fields."""
    print_section("Provenance Completeness")
    issues = check_provenance_completeness(catalog)
    if not issues:
        print("  All provenance sidecars are complete [OK]")
        return
    print(f"  {len(issues)} provenance record(s) with missing fields:")
    for item in issues:
        err_str = ", ".join(item.get("missing_fields", [item.get("error", "unknown")]))
        print(f"    [{item['source_project']}] {item['artifact_id']}: {err_str}")


def report_missing_metrics(catalog: CorpusCatalog) -> None:
    """Report artifacts with no fidelity/metrics."""
    print_section("Missing Metrics")
    missing = check_missing_metrics(catalog)
    if not missing:
        print("  All artifacts have at least one metric [OK]")
        return
    print(f"  {len(missing)} artifact(s) with no fidelity/phi_deviation/score/fixed_point:")
    for item in missing:
        print(f"    [{item['source_project']}] {item['artifact_id']} ({item['artifact_type']})")


def report_duplicates(catalog: CorpusCatalog) -> None:
    """Report duplicate artifact IDs."""
    print_section("Duplicate Artifact IDs")
    dups = check_duplicate_ids(catalog)
    if not dups:
        print("  No duplicate artifact IDs [OK]")
        return
    print(f"  {len(dups)} artifact ID(s) appear in multiple projects:")
    for item in dups:
        print(f"    {item['artifact_id']}: {', '.join(item['projects'])}")


def report_unlinked_sidecars(imports_dir: Path) -> None:
    """Report provenance files with no data file."""
    print_section("Unlinked Provenance Sidecars")
    unlinked = check_unlinked_sidecars(imports_dir)
    if not unlinked:
        print("  No unlinked provenance sidecars [OK]")
        return
    print(f"  {len(unlinked)} provenance sidecar(s) with no data file:")
    for item in unlinked:
        print(f"    {item['artifact_id']} ({item['project']})")


def report_routes(catalog: CorpusCatalog) -> None:
    """Report Sierpinski route distribution."""
    print_section("Sierpinski Routes")
    routes: Dict[str, int] = defaultdict(int)
    for entry in catalog.entries:
        if entry.artifact_type == "sierpinski_experiment":
            # Route is in the data file
            if entry.data_path:
                try:
                    with open(entry.data_path, encoding="utf-8") as f:
                        data = json.load(f)
                    route = data.get("route", "unknown")
                    routes[route] += 1
                except (json.JSONDecodeError, IOError):
                    routes["unknown"] += 1
    if not routes:
        print("  No Sierpinski experiments found")
        return
    for route, count in sorted(routes.items(), key=lambda x: -x[1]):
        print(f"    {route:<20} {count}")


def report_depth_distribution(catalog: CorpusCatalog) -> None:
    """Report depth/level distribution."""
    print_section("Depth / Level Distribution")
    depths: Dict[int, int] = defaultdict(int)
    for entry in catalog.entries:
        if entry.depth > 0:
            depths[entry.depth] += 1
    if not depths:
        print("  No depth information found")
        return
    print("  Depth  Count")
    print("  -----  -----")
    for depth in sorted(depths.keys()):
        print(f"    {depth:<4}  {depths[depth]}")


def report_evidence_class(catalog: CorpusCatalog) -> None:
    """Report artifact counts by evidence class."""
    print_section("Artifacts by Evidence Class")
    counts = check_by_evidence_class(catalog)
    if not counts:
        print("  No classification data found")
        return
    for k, v in sorted(counts.items()):
        print(f"    {k:<25} {v}")


def report_validation_tier(catalog: CorpusCatalog) -> None:
    """Report artifact counts by validation tier."""
    print_section("Artifacts by Validation Tier")
    counts = check_by_validation_tier(catalog)
    if not counts:
        print("  No classification data found")
        return
    tier_order = ["raw", "normalized", "benchmarked", "measured"]
    sorted_items = sorted(counts.items(), key=lambda x: tier_order.index(x[0]) if x[0] in tier_order else 99)
    for k, v in sorted_items:
        print(f"    {k:<25} {v}")


def report_backend_generation(catalog: CorpusCatalog) -> None:
    """Report artifact counts by backend generation."""
    print_section("Artifacts by Backend Generation")
    counts = check_by_backend_generation(catalog)
    if not counts:
        print("  No backend generation data found")
        return
    for k, v in sorted(counts.items()):
        print(f"    {k:<25} {v}")


def report_physical_calibration(catalog: CorpusCatalog) -> None:
    """Report hardware runs missing physical calibration."""
    print_section("Missing Physical Calibration")
    issues = check_missing_physical_calibration(catalog)
    if not issues:
        print("  All non-simulator hardware runs have physical calibration [OK]")
        return
    print(f"  {len(issues)} non-simulator artifact(s) missing physical calibration:")
    for item in sorted(issues, key=lambda x: x["backend"]):
        print(f"    [{item['source_project']}] {item['artifact_id']}")
        print(f"      backend={item['backend']} generation={item['backend_generation']}")
        print(f"      calibration={item['calibration_snapshot_id']}")
        print(f"      reason={item['reason']}")


def report_measured_tier_ready(catalog: CorpusCatalog) -> None:
    """Quality gate: report which artifacts qualify as 'measured-tier ready'.

    An artifact is measured-tier ready when ALL of:
    - provenance exists
    - at least one metric exists (fidelity, phi_deviation, sierpinski_score, or fixed_point)
    - backend is normalized (no 'ibm_' prefix mixed with 'ibmq_' on same backend)
    - calibration_completeness is at least 'metadata' (physical or metadata)
    """
    print_section("Quality Gate: Measured-Tier Ready")
    TIER_ORDER = ["raw", "normalized", "benchmarked", "measured"]

    ready = []
    not_ready = []

    for entry in catalog.entries:
        if not entry.data_path:
            continue
        data_path = Path(entry.data_path)
        if data_path.suffix != ".json":
            continue
        try:
            with open(data_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        reasons = []

        # 1. Provenance check
        if not entry.provenance_path:
            reasons.append("no provenance sidecar")

        # 2. Metrics check
        has_fidelity = data.get("fidelity") is not None
        has_phi = data.get("phi_deviation") is not None
        has_score = data.get("sierpinski_score") is not None
        has_fp = data.get("depth_invariant_fixed_point") is not None
        if not (has_fidelity or has_phi or has_score or has_fp):
            reasons.append("no metrics")

        # 3. Backend normalization check
        backend = data.get("backend", "")
        if backend.startswith("ibm_") and any(
            b.startswith("ibmq_") for b in [data.get("backend", "")]
        ):
            reasons.append("mixed backend naming")
        # Also flag known inconsistencies
        inconsistent_backends = {
            "ibm_perth", "ibm_guadalupe",
        }
        if backend in inconsistent_backends:
            reasons.append(f"non-normalized backend name '{backend}'")

        # 4. Calibration completeness check (for non-simulator hardware runs)
        backend_gen = data.get("backend_generation", "unknown")
        if backend_gen != "simulator":
            cal_id = data.get("calibration_snapshot_id")
            if cal_id:
                cal_found = False
                for e in catalog.entries:
                    if e.artifact_type == "calibration" and e.artifact_id == cal_id:
                        cal_path = Path(e.data_path)
                        if cal_path.exists():
                            try:
                                with open(cal_path, encoding="utf-8") as cf:
                                    cal_data = json.load(cf)
                                completeness = cal_data.get("calibration_completeness", "absent")
                                if completeness == "absent":
                                    reasons.append(f"calibration '{cal_id}' has completeness=absent")
                                cal_found = True
                            except (json.JSONDecodeError, IOError):
                                pass
                        break
                if not cal_found and not cal_id:
                    reasons.append("no calibration snapshot linked")
            else:
                reasons.append("no calibration_snapshot_id")

        if reasons:
            not_ready.append({
                "artifact_id": entry.artifact_id,
                "source_project": entry.source_project,
                "backend": backend,
                "reasons": reasons,
            })
        else:
            ready.append({
                "artifact_id": entry.artifact_id,
                "source_project": entry.source_project,
                "backend": backend,
            })

    print(f"  Measured-tier ready:  {len(ready)}")
    print(f"  NOT measured-tier:     {len(not_ready)}")
    if ready:
        print("  Ready:")
        for item in sorted(ready, key=lambda x: x["source_project"]):
            print(f"    [{item['source_project']}] {item['artifact_id']} ({item['backend']})")
    if not_ready:
        print("  Not ready:")
        for item in sorted(not_ready, key=lambda x: x["source_project"]):
            print(f"    [{item['source_project']}] {item['artifact_id']} ({item['backend']})")
            for reason in item["reasons"]:
                print(f"      - {reason}")


def report(imports_dir: Path, verbose: bool = False) -> None:
    """Generate and print the full corpus report."""
    print(f"\nGRE Research Corpus Report")
    print(f"  Imports directory: {imports_dir}")
    print(f"  Generated: {__import__('datetime').datetime.now().isoformat()}")

    catalog = discover_imports_dir(imports_dir)

    if verbose:
        report_summary(catalog, imports_dir)
    else:
        # Brief summary for non-verbose mode
        stats = catalog.stats()
        print_section("Corpus Summary")
        print(f"  Total artifacts:  {stats['total_artifacts']}")
        print(f"  Unique claims:    {stats['unique_claims']}")
        print(f"  Projects:        {', '.join(sorted(catalog.projects())) or '(none)'}")

    report_missing_provenance(catalog)
    report_provenance_completeness(catalog)
    report_missing_metrics(catalog)
    report_duplicates(catalog)
    report_unlinked_sidecars(imports_dir)
    report_evidence_class(catalog)
    report_validation_tier(catalog)
    report_backend_generation(catalog)
    report_physical_calibration(catalog)

    if verbose:
        report_routes(catalog)
        report_depth_distribution(catalog)
        report_measured_tier_ready(catalog)

    print()  # blank line at end


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Print a diagnostic report on the GRE research corpus.",
    )
    parser.add_argument(
        "--imports", "-i",
        type=Path,
        default=Path(__file__).parent.parent.parent / "imports",
        help="Path to imports/ directory (default: <gre>/imports)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Include detailed breakdowns (routes, depth distribution, by-project stats)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output catalog as JSON instead of human-readable report",
    )

    args = parser.parse_args()

    catalog = discover_imports_dir(args.imports)

    if args.json:
        output = catalog.to_dict()
        output["diagnostics"] = {
            "missing_provenance": check_missing_provenance(catalog),
            "missing_metrics": check_missing_metrics(catalog),
            "duplicates": check_duplicate_ids(catalog),
            "unlinked_sidecars": check_unlinked_sidecars(args.imports),
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0

    report(args.imports, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
