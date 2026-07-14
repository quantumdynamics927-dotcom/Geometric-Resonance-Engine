"""End-to-end tests for the research corpus ingestion pipeline.

Tests cover:
- Provenance preservation through the import pipeline
- Schema validation for all record types
- Mixed-format ingestion (JSON, Markdown, CSV)
- Missing-field handling with appropriate defaults
- Deterministic normalization (same input → same output)
- Full load_corpus integration
"""

import json
import tempfile
import os
from pathlib import Path
from datetime import datetime
import pytest

from gre.research import (
    load_corpus,
    list_projects,
    query_runs,
    query_sierpinski,
    compare_to_generated,
    get_claim,
    evidence_chain,
)
from gre.research.catalog import CorpusCatalog, discover_imports_dir
from gre.research import normalizers
from gre.research import linkage
from gre.research.schemas import (
    HardwareRunRecord,
    SierpinskiExperimentRecord,
    CalibrationSnapshot,
    ExperimentTag,
)
from gre.research.provenance import ProvenanceSidecar, TransformStep
from gre.research.linkage import ClaimLinkage, ImportedClaimRecord


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_imports_dir(tmp_path):
    """Create a temporary imports directory with test artifacts."""
    import_dir = tmp_path / "imports"
    import_dir.mkdir()
    project_dir = import_dir / "test_project"
    project_dir.mkdir()

    # JSON hardware run
    hw_run = {
        "experiment_id": "test-run-001",
        "project": "test_project",
        "date": "2024-03-15",
        "backend": "ibmq_qasm_simulator",
        "hypothesis_tag": "sierpinski_depth_invariant",
        "circuit_family": "fractal_walk",
        "depth": 5,
        "shots": 1024,
        "qubit_count": 33,
        "fidelity": 0.891,
        "phi_deviation": 0.0015,
        "sierpinski_score": 0.904,
        "notes": "Test hardware run",
    }
    hw_path = project_dir / "test-run-001.json"
    hw_path.write_text(json.dumps(hw_run, indent=2), encoding="utf-8")

    # Provenance sidecar
    prov = {
        "artifact_id": "test-run-001",
        "source_project": "test_project",
        "source_artifact_id": "test-run-001",
        "source_path": "test/results/run001.json",
        "source_commit": "a1b2c3d",
        "source_date": "2024-03-15",
        "import_date": datetime.utcnow().isoformat() + "Z",
        "import_method": "json_import",
        "sensitivity": "internal",
        "transform_chain": [
            {"step_id": 0, "transform_type": "parse", "description": "JSON → dict", "parameters": {}},
        ],
        "claims_supported": ["test_claim_1"],
    }
    prov_path = project_dir / "test-run-001.provenance.json"
    prov_path.write_text(json.dumps(prov, indent=2), encoding="utf-8")

    # Markdown Sierpinski experiment
    md_content = """---
experiment_id: sierpinski-level3-test
project: test_project
date: 2024-03-10
backend: ibmq_qasm_simulator
recursion_level: 3
route: ifs
depth: 3
shots: 2048
qubit_count: 27
fidelity: 0.875
depth_invariant_fixed_point: 0.619
depth_invariant_confidence: 0.91
void_encoding_used: true
hausdorff_dimension: 1.585
---

# Sierpinski Level 3 — IFS Route

## Claims
- Depth-invariant fixed point at 1/φ ≈ 0.618 confirmed
- Void region used as decoherence-free subspace

## Key Metrics
| Metric | Value |
|--------|-------|
| Fidelity | 0.875 |
| φ deviation | 0.002 |
| Sierpinski score | 0.901 |
"""
    md_path = project_dir / "sierpinski-level3-test.summary.md"
    md_path.write_text(md_content, encoding="utf-8")

    # JSON data file paired with markdown summary
    sier_md_data = {
        "experiment_id": "sierpinski-level3-test",
        "project": "test_project",
        "date": "2024-03-10",
        "backend": "ibmq_qasm_simulator",
        "recursion_level": 3,
        "route": "ifs",
        "depth": 3,
        "shots": 2048,
        "qubit_count": 27,
        "fidelity": 0.875,
        "depth_invariant_fixed_point": 0.619,
        "depth_invariant_confidence": 0.91,
        "void_encoding_used": True,
        "hausdorff_dimension": 1.585,
    }
    sier_md_json_path = project_dir / "sierpinski-level3-test.json"
    sier_md_json_path.write_text(json.dumps(sier_md_data), encoding="utf-8")

    # Sierpinski JSON
    sier_data = {
        "experiment_id": "sierpinski-level4-test",
        "project": "test_project",
        "date": "2024-04-01",
        "backend": "ibmq_qasm_simulator",
        "recursion_level": 4,
        "route": "pascal",
        "depth": 4,
        "shots": 4096,
        "qubit_count": 81,
        "fidelity": 0.862,
        "depth_invariant_fixed_point": 0.6175,
        "depth_invariant_confidence": 0.88,
        "void_encoding_used": False,
    }
    sier_path = project_dir / "sierpinski-level4-test.json"
    sier_path.write_text(json.dumps(sier_data, indent=2), encoding="utf-8")

    # Calibration JSON
    cal_data = {
        "snapshot_id": "cal-test-001",
        "backend": "ibmq_qasm_simulator",
        "timestamp": "2024-03-01T10:00:00Z",
        "t1_times": {"0": 95.3, "1": 87.2, "2": 91.1},
        "t2_times": {"0": 150.1, "1": 142.8, "2": 148.5},
        "readout_errors": {"0": 0.015, "1": 0.022, "2": 0.018},
        "gate_errors": {"0": 0.001, "1": 0.002, "2": 0.001},
        "qubit_freqs": {"0": 5.1e9, "1": 5.2e9, "2": 5.15e9},
    }
    cal_path = import_dir / "calibration" / "cal-test-001.json"
    cal_path.parent.mkdir(exist_ok=True)
    cal_path.write_text(json.dumps(cal_data, indent=2), encoding="utf-8")

    return import_dir


# =============================================================================
# Test: Provenance preservation
# =============================================================================

class TestProvenancePreservation:
    def test_hardware_run_provenance_preserved(self, temp_imports_dir):
        """Source_project, commit, and transform chain survive normalization."""
        corpus, catalog, stats = load_corpus(temp_imports_dir, force_reload=True)

        run = corpus.hardware_runs.get("test-run-001")
        assert run is not None
        assert run.provenance.source_project == "test_project"
        assert run.provenance.source_commit == "a1b2c3d"
        assert run.provenance.source_path == "test/results/run001.json"
        assert len(run.provenance.transform_chain) >= 1
        assert "test_claim_1" in run.provenance.claims_supported

    def test_import_date_set(self, temp_imports_dir):
        """Import date is recorded even when source date is absent."""
        corpus, catalog, stats = load_corpus(temp_imports_dir, force_reload=True)

        # The calibration has explicit import date
        cal = corpus.calibrations.get("cal-test-001")
        assert cal is not None
        assert cal.provenance.import_date != ""


# =============================================================================
# Test: Schema validation
# =============================================================================

class TestSchemaValidation:
    def test_hardware_run_record_fields(self, temp_imports_dir):
        """All required HardwareRunRecord fields are populated."""
        corpus, catalog, stats = load_corpus(temp_imports_dir, force_reload=True)

        run = corpus.hardware_runs.get("test-run-001")
        assert isinstance(run, HardwareRunRecord)
        assert run.metadata.experiment_id == "test-run-001"
        assert run.backend == "ibmq_qasm_simulator"
        assert run.qubit_count == 33
        assert run.depth == 5
        assert run.shots == 1024
        assert run.fidelity == 0.891
        assert run.phi_deviation == 0.0015
        assert run.sierpinski_score == 0.904

    def test_sierpinski_experiment_record_fields(self, temp_imports_dir):
        """All SierpinskiExperimentRecord fields are populated."""
        corpus, catalog, stats = load_corpus(temp_imports_dir, force_reload=True)

        exp = corpus.sierpinski_experiments.get("sierpinski-level3-test")
        assert exp is not None
        assert isinstance(exp, SierpinskiExperimentRecord)
        assert exp.recursion_level == 3
        assert exp.route == "ifs"
        assert abs(exp.depth_invariant_fixed_point - 0.619) < 0.01
        assert exp.depth_invariant_confidence == 0.91
        assert exp.void_encoding_used is True

    def test_calibration_snapshot_fields(self, temp_imports_dir):
        """All CalibrationSnapshot fields are populated."""
        corpus, catalog, stats = load_corpus(temp_imports_dir, force_reload=True)

        cal = corpus.calibrations.get("cal-test-001")
        assert cal is not None
        assert isinstance(cal, CalibrationSnapshot)
        assert cal.backend == "ibmq_qasm_simulator"
        assert cal.t1_times.get("0") == 95.3
        assert cal.t2_times.get("1") == 142.8


# =============================================================================
# Test: Mixed-format ingestion
# =============================================================================

class TestMixedFormatIngestion:
    def test_json_hardware_run_loaded(self, temp_imports_dir):
        """JSON artifact is correctly loaded."""
        corpus, catalog, stats = load_corpus(temp_imports_dir, force_reload=True)
        assert "test-run-001" in corpus.hardware_runs

    def test_markdown_sierpinski_loaded(self, temp_imports_dir):
        """Markdown Sierpinski summary is correctly loaded."""
        corpus, catalog, stats = load_corpus(temp_imports_dir, force_reload=True)
        assert "sierpinski-level3-test" in corpus.sierpinski_experiments

    def test_json_sierpinski_loaded(self, temp_imports_dir):
        """JSON Sierpinski artifact is correctly loaded."""
        corpus, catalog, stats = load_corpus(temp_imports_dir, force_reload=True)
        assert "sierpinski-level4-test" in corpus.sierpinski_experiments

    def test_calibration_json_loaded(self, temp_imports_dir):
        """JSON calibration snapshot is correctly loaded."""
        corpus, catalog, stats = load_corpus(temp_imports_dir, force_reload=True)
        assert "cal-test-001" in corpus.calibrations

    def test_catalog_entry_count(self, temp_imports_dir):
        """Catalog contains all non-sidecar artifacts."""
        corpus, catalog, stats = load_corpus(temp_imports_dir, force_reload=True)
        # 3 test_project entries + 1 calibration entry = 4
        # (the markdown file is a sidecar, not a primary artifact)
        assert len(catalog.entries) == 4  # 3 in test_project + 1 in calibration
        assert stats.total_entries == 4


# =============================================================================
# Test: Missing-field handling
# =============================================================================

class TestMissingFieldHandling:
    def test_minimal_hardware_run_normalizes(self):
        """A hardware run with only experiment_id normalizes without error."""
        minimal_data = {"experiment_id": "minimal-001"}
        result = normalizers.normalize_hardware_run(minimal_data, source_project="test")

        assert result.record.metadata.experiment_id == "minimal-001"
        assert result.record.backend == "unknown"  # default
        assert len(result.warnings) >= 0  # warnings are acceptable

    def test_sierpinski_defaults(self):
        """Missing Sierpinski fields get correct defaults."""
        minimal_data = {"experiment_id": "sier-minimal", "recursion_level": 3}
        result = normalizers.normalize_sierpinski_experiment(minimal_data)

        assert result.record.recursion_level == 3
        assert result.record.route == "ifs"  # default
        assert result.record.void_encoding_used is False  # default

    def test_calibration_minimal_normalizes(self):
        """Calibration with minimal fields normalizes without error."""
        minimal_data = {"snapshot_id": "cal-minimal"}
        result = normalizers.normalize_calibration_snapshot(minimal_data)

        assert result.record.snapshot_id == "cal-minimal"
        assert result.record.backend == "unknown"  # default

    def test_unknown_hypothesis_tag_defaults_to_other(self):
        """An unrecognized hypothesis tag becomes ExperimentTag.OTHER."""
        data = {"experiment_id": "unknown-tag", "hypothesis_tag": "completely_unknown_nonsense_tag"}
        result = normalizers.normalize_hardware_run(data)
        assert result.record.metadata.hypothesis_tag == ExperimentTag.OTHER


# =============================================================================
# Test: Deterministic normalization
# =============================================================================

class TestDeterministicNormalization:
    def test_same_input_produces_same_output(self):
        """Normalizing the same data twice yields identical records."""
        data = {
            "experiment_id": "det-001",
            "project": "test",
            "backend": "ibmq_qasm_simulator",
            "depth": 5,
            "shots": 1024,
            "fidelity": 0.891,
        }

        r1 = normalizers.normalize_hardware_run(data, source_project="test")
        r2 = normalizers.normalize_hardware_run(data, source_project="test")

        # Compare key fields that should be identical
        assert r1.record.metadata.experiment_id == r2.record.metadata.experiment_id
        assert r1.record.backend == r2.record.backend
        assert r1.record.depth == r2.record.depth
        assert r1.record.fidelity == r2.record.fidelity
        assert r1.record.metadata.hypothesis_tag == r2.record.metadata.hypothesis_tag

    def test_alias_fields_normalize_correctly(self):
        """Different field name spellings all map to canonical names."""
        variants = [
            {"experiment_id": "alias-001", "depth": 5},
            {"experimentId": "alias-001", "depth": 5},
            {"run_id": "alias-001", "depth": 5},
            {"id": "alias-001", "circuit_depth": 5},
        ]

        results = [normalizers.normalize_hardware_run(v, source_project="test") for v in variants]
        depths = [r.record.depth for r in results]
        assert len(set(depths)) == 1, f"Depths not consistent: {depths}"


# =============================================================================
# Test: Linkage
# =============================================================================

class TestClaimLinkage:
    def test_register_and_retrieve_claim(self):
        """Claims can be registered and retrieved by ID."""
        linkage = ClaimLinkage()
        claim = ImportedClaimRecord(
            claim_id="test_claim_001",
            claim_type=ExperimentTag.SIERPINSKI_DEPTH_INVARIANT,
            description="Test claim",
            hypothesis="Fixed point at 1/φ",
            evidence=["exp-001"],
            source_artifacts=["exp-001"],
            confidence=0.9,
        )
        linkage.register_claim(claim)

        retrieved = linkage.get_claim("test_claim_001")
        assert retrieved is not None
        assert retrieved.claim_id == "test_claim_001"
        assert retrieved.confidence == 0.9

    def test_artifact_to_claim_mapping(self):
        """Linking an artifact to a claim is retrievable both ways."""
        linkage = ClaimLinkage()
        claim = ImportedClaimRecord(
            claim_id="link-test",
            claim_type=ExperimentTag.FIXED_POINT_1_OVER_PHI,
            description="Link test",
            hypothesis="1/φ fixed point",
            evidence=["run-001"],
            source_artifacts=["run-001"],
            confidence=0.85,
        )
        linkage.register_claim(claim)

        artifacts = linkage.artifacts_for_claim("link-test")
        assert "run-001" in artifacts

        claims = linkage.claims_for_artifact("run-001")
        assert "link-test" in claims


# =============================================================================
# Test: Module-level API
# =============================================================================

class TestModuleLevelAPI:
    def test_list_projects(self, temp_imports_dir):
        """list_projects returns project names."""
        corpus, catalog, stats = load_corpus(temp_imports_dir, force_reload=True)
        projects = list_projects(corpus)
        assert "test_project" in projects

    def test_query_runs_filter(self, temp_imports_dir):
        """query_runs with filters returns correct subset."""
        corpus, catalog, stats = load_corpus(temp_imports_dir, force_reload=True)
        runs = query_runs(depth=5, corpus=corpus)
        assert all(r.depth == 5 for r in runs)

    def test_query_sierpinski_by_route(self, temp_imports_dir):
        """query_sierpinski filters by route."""
        corpus, catalog, stats = load_corpus(temp_imports_dir, force_reload=True)
        experiments = query_sierpinski(route="ifs", corpus=corpus)
        assert all(e.route == "ifs" for e in experiments)

    def test_compare_to_generated_returns_comparison(self, temp_imports_dir):
        """compare_to_generated returns a GeneratedComparison."""
        corpus, catalog, stats = load_corpus(temp_imports_dir, force_reload=True)
        comparison = compare_to_generated(
            corpus=corpus,
            graph_nodes=33,
            depth=5,
            backend="ibmq_qasm_simulator",
            fidelity=0.891,
        )
        assert isinstance(comparison, linkage.GeneratedComparison)
        assert comparison.generated_descriptor["graph_nodes"] == 33

    def test_get_claim_retrieves_claim(self, temp_imports_dir):
        """get_claim returns ImportedClaimRecord when found."""
        corpus, catalog, stats = load_corpus(temp_imports_dir, force_reload=True)
        claim = get_claim("test_claim_1")
        assert claim is not None
        assert claim.claim_id == "test_claim_1"

    def test_evidence_chain_builds(self, temp_imports_dir):
        """evidence_chain returns complete chain for a known claim."""
        corpus, catalog, stats = load_corpus(temp_imports_dir, force_reload=True)
        chain = evidence_chain("test_claim_1", corpus=corpus)
        assert "claim" in chain
        assert chain["claim"]["claim_id"] == "test_claim_1"


# =============================================================================
# Test: Catalog discovery
# =============================================================================

class TestCatalogDiscovery:
    def test_discover_imports_dir_finds_artifacts(self, temp_imports_dir):
        """discover_imports_dir scans and indexes all artifacts."""
        catalog = discover_imports_dir(temp_imports_dir)
        assert len(catalog.entries) >= 4
        assert catalog.entries[0].artifact_id != ""

    def test_catalog_search(self, temp_imports_dir):
        """Catalog search applies multiple filters."""
        catalog = discover_imports_dir(temp_imports_dir)
        results = catalog.search(artifact_type="sierpinski_experiment")
        assert all(e.artifact_type == "sierpinski_experiment" for e in results)

    def test_catalog_by_project(self, temp_imports_dir):
        """catalog.by_project() returns only that project's entries."""
        catalog = discover_imports_dir(temp_imports_dir)
        entries = catalog.by_project("test_project")
        assert all(e.source_project == "test_project" for e in entries)

    def test_catalog_save_load_roundtrip(self, temp_imports_dir, tmp_path):
        """Catalog can be saved and reloaded without data loss."""
        catalog = discover_imports_dir(temp_imports_dir)
        save_path = tmp_path / "catalog.json"
        catalog.save(save_path)

        loaded = CorpusCatalog.load(save_path)
        assert len(loaded.entries) == len(catalog.entries)
        ids_loaded = {e.artifact_id for e in loaded.entries}
        ids_original = {e.artifact_id for e in catalog.entries}
        assert ids_loaded == ids_original


# =============================================================================
# Test: Fixed-point comparison
# =============================================================================

class TestFixedPointComparison:
    def test_compare_sierpinski_fixed_point_theory_match(self, temp_imports_dir):
        """Observations within 5% of 1/φ are marked consistent."""
        corpus, catalog, stats = load_corpus(temp_imports_dir)
        linker = linkage.OutputLinker(corpus, linkage.ClaimLinkage())
        result = linker.compare_sierpinski_fixed_point(0.619, tolerance=0.05)
        assert result["consistent_with_theory"] is True
        assert result["within_5pct"] is True

    def test_compare_sierpinski_fixed_point_theory_mismatch(self, temp_imports_dir):
        """Observations far from 1/φ are marked inconsistent."""
        corpus, catalog, stats = load_corpus(temp_imports_dir)
        linker = linkage.OutputLinker(corpus, linkage.ClaimLinkage())
        result = linker.compare_sierpinski_fixed_point(0.75, tolerance=0.05)
        assert result["consistent_with_theory"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
