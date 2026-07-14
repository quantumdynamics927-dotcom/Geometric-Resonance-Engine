#!/usr/bin/env python3
"""First corpus query -- demonstrating the GRE research corpus API.

Run with:
    python examples/first_corpus_query.py

This script demonstrates:
1. Loading the corpus with force_reload=True
2. Listing available projects
3. Querying QSG hardware runs by backend
4. Querying Sierpinski records by recursion level
5. Comparing a generated graph descriptor to imported evidence
6. Printing the evidence chain for an imported claim
"""

import sys
from pathlib import Path

# Ensure gre is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from gre.research import (
    load_corpus,
    list_projects,
    query_runs,
    query_sierpinski,
    compare_to_generated,
    get_claim,
    evidence_chain,
)


def main():
    print("=" * 70)
    print("  GRE Research Corpus -- First Query")
    print("=" * 70)

    # -------------------------------------------------------------------------
    # 1. Load the corpus
    # -------------------------------------------------------------------------
    print("\n[1] Loading corpus...")
    imports_path = Path(__file__).parent.parent / "imports"
    corpus, catalog, stats = load_corpus(imports_dir=imports_path, force_reload=True)

    print(f"    Loaded {stats.total_entries} artifacts")
    print(f"      Hardware runs:       {stats.hardware_runs_loaded}")
    print(f"      Sierpinski exp:      {stats.sierpinski_experiments_loaded}")
    print(f"      Calibration snaps:   {stats.calibrations_loaded}")
    if stats.errors > 0:
        print(f"      Errors:             {stats.errors}")

    # -------------------------------------------------------------------------
    # 2. List projects
    # -------------------------------------------------------------------------
    print("\n[2] Projects in corpus:")
    projects = list_projects(corpus=corpus)
    if projects:
        for p in projects:
            entries = catalog.by_project(p)
            print(f"    {p:<20} {len(entries)} artifacts")
    else:
        print("    (no projects -- import artifacts to see them here)")

    # -------------------------------------------------------------------------
    # 3. Query QSG runs by backend
    # -------------------------------------------------------------------------
    print("\n[3] QSG hardware runs by backend:")
    all_runs = query_runs(corpus=corpus)
    by_backend: dict = {}
    for run in all_runs:
        b = run.backend or "unknown"
        if b not in by_backend:
            by_backend[b] = []
        by_backend[b].append(run)

    for backend, runs in sorted(by_backend.items()):
        print(f"\n    Backend: {backend}")
        for run in runs[:5]:  # show first 5 per backend
            fid = f"{run.fidelity:.3f}" if run.fidelity is not None else "N/A"
            phi = f"{run.phi_deviation:.4f}" if run.phi_deviation is not None else "N/A"
            print(f"      {run.metadata.experiment_id:<25} depth={run.depth:<4} fidelity={fid} phi_dev={phi}")
        if len(runs) > 5:
            print(f"      ... and {len(runs) - 5} more")

    # -------------------------------------------------------------------------
    # 4. Query Sierpinski experiments by depth/level
    # -------------------------------------------------------------------------
    print("\n[4] Sierpinski experiments by recursion level:")
    all_experiments = query_sierpinski(corpus=corpus)
    if all_experiments:
        by_level: dict = {}
        for exp in all_experiments:
            lvl = exp.recursion_level
            if lvl not in by_level:
                by_level[lvl] = []
            by_level[lvl].append(exp)

        for level in sorted(by_level.keys()):
            exps = by_level[level]
            print(f"\n    Level {level} ({len(exps)} experiment{'s' if len(exps) > 1 else ''})")
            for exp in exps:
                fp = f"{exp.depth_invariant_fixed_point:.4f}" if exp.depth_invariant_fixed_point is not None else "N/A"
                conf = f"{exp.depth_invariant_confidence:.2f}" if exp.depth_invariant_confidence is not None else "N/A"
                print(f"      {exp.experiment_id:<30} route={exp.route:<10} fp={fp} conf={conf}")
    else:
        print("    (no Sierpinski experiments -- add artifacts to see them here)")

    # -------------------------------------------------------------------------
    # 5. Compare a generated graph to historical evidence
    # -------------------------------------------------------------------------
    print("\n[5] Compare generated Sierpinski (level 3) to historical evidence:")

    # Simulate a generated result: 33-node graph at level 5 (depth=5), fidelity 0.89
    # This should match qsg-run-042 (33 nodes, depth=5, ibmq_qasm_simulator, fidelity=0.918)
    comparison = compare_to_generated(
        corpus=corpus,
        graph_nodes=33,
        depth=5,
        backend="ibmq_qasm_simulator",
        fidelity=0.891,
        phi_deviation=0.0015,
        sierpinski_score=0.904,
        route="ifs",
        tolerance=0.15,
    )

    print(f"\n    Generated descriptor:")
    for k, v in comparison.generated_descriptor.items():
        print(f"      {k}: {v}")

    print(f"\n    Matching historical records: {len(comparison.matching_records)}")
    if comparison.matching_records:
        best = comparison.best_match
        print(f"    Best match: {best.metadata.experiment_id if best else 'none'}")
        print(f"    Best match similarity: {comparison.best_match_similarity:.3f}" if comparison.best_match_similarity is not None else "")
        print(f"    Avg fidelity of matches: {comparison.avg_fidelity:.3f}" if comparison.avg_fidelity is not None else "    Avg fidelity: N/A")
        print(f"    Avg phi deviation: {comparison.avg_phi_deviation:.4f}" if comparison.avg_phi_deviation is not None else "    Avg phi deviation: N/A")
    else:
        print("    (no matching records found)")

    print(f"\n    Evidence for claims: {', '.join(comparison.claim_supported) if comparison.claim_supported else '(none)'}")
    print(f"    Linkage strength: {comparison.linkage_strength:.2f}")

    # -------------------------------------------------------------------------
    # 6. Evidence chain for one claim
    # -------------------------------------------------------------------------
    print("\n[6] Evidence chain for imported claims:")

    # Get the first claim we can find
    claim_ids_found = []
    for run in list(corpus.hardware_runs.values())[:10]:
        for cid in run.provenance.claims_supported:
            if cid not in claim_ids_found:
                claim_ids_found.append(cid)
    for exp in list(corpus.sierpinski_experiments.values())[:10]:
        for cid in exp.hardware_record.provenance.claims_supported:
            if cid not in claim_ids_found:
                claim_ids_found.append(cid)

    if claim_ids_found:
        claim_id = claim_ids_found[0]
        print(f"\n    Claim ID: {claim_id}")

        # Show claim details
        claim = get_claim(claim_id)
        if claim:
            print(f"    Type:        {claim.claim_type.value}")
            print(f"    Hypothesis: {claim.hypothesis}")
            print(f"    Confidence: {claim.confidence:.2f}" if claim.confidence else "    Confidence: N/A")
            print(f"    Description: {claim.description}")
            print(f"    Source artifacts: {', '.join(claim.source_artifacts) if claim.source_artifacts else '(none)'}")
        else:
            print(f"    (claim record not in linkage registry)")

        # Build evidence chain
        chain = evidence_chain(claim_id, corpus=corpus)
        if "error" not in chain:
            print(f"\n    Evidence chain:")
            print(f"      Supporting artifacts: {chain['evidence_strength']}")
            for artifact in chain.get("supporting_artifacts", []):
                # HardwareRunRecord.to_dict() flattens experiment_id to top level
                # SierpinskiExperimentRecord.to_dict() also flattens it from metadata
                eid = artifact.get("experiment_id") or artifact.get("metadata", {}).get("experiment_id", "unknown")
                fid = artifact.get("fidelity", "N/A")
                print(f"        - {eid}: fidelity={fid}")
            print(f"      Calibration context: {len(chain.get('calibration_context', []))}")
        else:
            print(f"\n    Chain error: {chain['error']}")
    else:
        print("\n    (no claims found in loaded corpus)")
        print("    Import artifacts with provenance.claims_supported to see evidence chains")

    # -------------------------------------------------------------------------
    # Summary stats
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  Done. Corpus is ready for hypothesis-driven queries.")
    print("=" * 70)


if __name__ == "__main__":
    main()
