"""Research corpus integration — ingestion, normalization, and provenance.

The research module provides tools for importing, normalizing, and querying
prior experimental results from QSG, Sierpinski, calibration, and other
prior projects into GRE as canonical imported evidence.

Quick start::

    from gre.research import load_corpus, list_projects

    # Load all imported artifacts
    corpus, catalog, stats = load_corpus()

    # List available projects
    projects = list_projects(corpus)

    # Query hardware runs
    runs = corpus.find_runs(depth=5, backend="ibmq_qasm_simulator")

    # Compare a new result to historical runs
    from gre.research import compare_to_generated
    comparison = compare_to_generated(
        corpus=corpus,
        graph_nodes=33,
        depth=3,
        backend="ibmq_qasm_simulator",
        fidelity=0.891,
    )
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from .schemas import (
    HardwareRunRecord,
    SierpinskiExperimentRecord,
    CalibrationSnapshot,
    ProvenanceSidecar,
    ArtifactDescriptor,
    ExperimentMetadata,
    ExperimentTag,
    CircuitFamily,
    BackendName,
    EvidenceClass,
    ValidationTier,
    BackendGeneration,
    CalibrationCompleteness,
)
from .provenance import ProvenanceChain, TransformStep
from .artifacts import ArtifactModel, ArtifactRegistry
from .corpus import ResearchCorpus, load_project_corpus
from .catalog import CorpusCatalog, CatalogEntry, discover_imports_dir
from .loader import LoadStats
from . import loader
from . import calibration_fetch
from . import normalizers
from . import linkage
from .linkage import (
    ImportedClaimRecord,
    ClaimLinkage,
    EvidenceLink,
    OutputLinker,
    GeneratedComparison,
)


# -----------------------------------------------------------------------------
# Module-level corpus access
# -----------------------------------------------------------------------------

_CORPUS: Optional[ResearchCorpus] = None
_CATALOG: Optional[CorpusCatalog] = None
_LINKAGE: Optional[ClaimLinkage] = None
_CACHED_STATS: Optional[loader.LoadStats] = None


def _ensure_loaded(
    imports_dir: Optional[Path] = None,
) -> Tuple[ResearchCorpus, CorpusCatalog, ClaimLinkage]:
    """Lazily load the corpus on first access."""
    global _CORPUS, _CATALOG, _LINKAGE
    if _CORPUS is None:
        _CORPUS, _CATALOG, _stats = loader.load_corpus(imports_dir)
        _LINKAGE = ClaimLinkage()
        # Register claims from provenance sidecars
        _register_claims_from_corpus(_CORPUS, _LINKAGE)
    return _CORPUS, _CATALOG, _LINKAGE


def _register_claims_from_corpus(
    corpus: ResearchCorpus,
    linkage: ClaimLinkage,
) -> None:
    """Populate ClaimLinkage from corpus provenance sidecars."""
    for run in corpus.hardware_runs.values():
        for claim_id in run.provenance.claims_supported:
            record = ImportedClaimRecord(
                claim_id=claim_id,
                claim_type=run.metadata.hypothesis_tag,
                description=f"Claim {claim_id} from {run.metadata.project}",
                hypothesis=run.metadata.hypothesis_tag.value,
                evidence=[run.metadata.experiment_id],
                source_artifacts=[run.metadata.experiment_id],
                confidence=run.fidelity or 0.0,
                provenance=run.provenance,
            )
            linkage.register_claim(record)

    for exp in corpus.sierpinski_experiments.values():
        for claim_id in exp.hardware_record.provenance.claims_supported:
            record = ImportedClaimRecord(
                claim_id=claim_id,
                claim_type=exp.hardware_record.metadata.hypothesis_tag,
                description=f"Claim {claim_id} from Sierpinski experiment",
                hypothesis=exp.hardware_record.metadata.hypothesis_tag.value,
                evidence=[exp.hardware_record.metadata.experiment_id],
                source_artifacts=[exp.hardware_record.metadata.experiment_id],
                confidence=exp.depth_invariant_confidence or exp.hardware_record.fidelity or 0.0,
                provenance=exp.hardware_record.provenance,
            )
            linkage.register_claim(record)


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def load_corpus(
    imports_dir: Optional[Path] = None,
    force_reload: bool = False,
) -> Tuple[ResearchCorpus, CorpusCatalog, loader.LoadStats]:
    """Load the full research corpus.

    Discovers all artifacts in ``imports_dir``, normalizes them to canonical
    record types, and returns the populated ResearchCorpus along with the
    catalog and load statistics.

    Args:
        imports_dir: Path to the ``imports/`` directory. Defaults to
            ``<gre>/research/imports/`` (i.e. ``imports/`` at the repo root).
        force_reload: If True, ignore any cached catalog and rebuild from disk.

    Returns:
        Tuple of ``(corpus, catalog, stats)`` where:

        - ``corpus`` is a populated :class:`ResearchCorpus`
        - ``catalog`` is a :class:`CorpusCatalog` with all discovered entries
        - ``stats`` is a :class:`LoadStats` with load counts and any errors

    Example::

        corpus, catalog, stats = load_corpus()
        print(f"Loaded {stats.hardware_runs_loaded} hardware runs")
        for project in catalog.projects():
            print(f"  {project}: {len(catalog.by_project(project))} artifacts")
    """
    global _CORPUS, _CATALOG, _LINKAGE, _CACHED_STATS
    if force_reload:
        _CORPUS = None
        _CATALOG = None
        _LINKAGE = None
        _CACHED_STATS = None

    if _CORPUS is None:
        _CORPUS, _CATALOG, _CACHED_STATS = loader.load_corpus(
            imports_dir=imports_dir,
            skip_cache=force_reload,
        )
        _LINKAGE = ClaimLinkage()
        _register_claims_from_corpus(_CORPUS, _LINKAGE)

    return _CORPUS, _CATALOG, _CACHED_STATS


def list_projects(corpus: Optional[ResearchCorpus] = None) -> List[str]:
    """List all source projects in the corpus.

    Args:
        corpus: Optional corpus. If None, uses the lazily-loaded global corpus.

    Returns:
        List of project names (e.g., ``["qsg", "sierpinski", "calibration"]``).
    """
    if corpus is None:
        corpus, _, _ = _ensure_loaded()
    return list(corpus.stats().projects)


def query_runs(
    depth: Optional[int] = None,
    backend: Optional[str] = None,
    project: Optional[str] = None,
    hypothesis_tag: Optional[ExperimentTag] = None,
    corpus: Optional[ResearchCorpus] = None,
    min_qubits: Optional[int] = None,
    max_qubits: Optional[int] = None,
    min_fidelity: Optional[float] = None,
) -> List[HardwareRunRecord]:
    """Query hardware runs matching the given filters.

    All filter arguments are combined with AND logic — a run must match
    every non-None filter to be returned.

    Args:
        depth: Exact circuit depth to match.
        backend: Exact backend name to match.
        project: Exact project name to match.
        hypothesis_tag: ExperimentTag enum value to match.
        corpus: Optional corpus. If None, uses the lazily-loaded global corpus.
        min_qubits: Minimum qubit count.
        max_qubits: Maximum qubit count.
        min_fidelity: Minimum fidelity threshold.

    Returns:
        List of matching :class:`HardwareRunRecord` objects.

    Example::

        runs = query_runs(depth=5, backend="ibmq_qasm_simulator")
        for run in runs:
            print(f"{run.metadata.experiment_id}: fidelity={run.fidelity}")
    """
    if corpus is None:
        corpus, _, _ = _ensure_loaded()
    return corpus.find_runs(
        depth=depth,
        backend=backend,
        project=project,
        hypothesis_tag=hypothesis_tag,
        min_qubits=min_qubits,
        max_qubits=max_qubits,
        min_fidelity=min_fidelity,
    )


def query_sierpinski(
    route: Optional[str] = None,
    min_level: Optional[int] = None,
    corpus: Optional[ResearchCorpus] = None,
) -> List[SierpinskiExperimentRecord]:
    """Query Sierpinski experiments matching the given filters.

    Args:
        route: Mathematical route name to match (e.g., ``"ifs"``, ``"pascal"``).
        min_level: Minimum recursion level.
        corpus: Optional corpus. If None, uses the lazily-loaded global corpus.

    Returns:
        List of matching :class:`SierpinskiExperimentRecord` objects.
    """
    if corpus is None:
        corpus, _, _ = _ensure_loaded()
    experiments = corpus.find_sierpinski_experiments()

    if route is not None:
        experiments = [e for e in experiments if e.route == route]
    if min_level is not None:
        experiments = [e for e in experiments if e.recursion_level >= min_level]

    return experiments


def compare_to_generated(
    graph_nodes: int,
    depth: int,
    backend: str,
    project: Optional[str] = None,
    fidelity: Optional[float] = None,
    phi_deviation: Optional[float] = None,
    sierpinski_score: Optional[float] = None,
    route: str = "ifs",
    corpus: Optional[ResearchCorpus] = None,
    tolerance: float = 0.1,
) -> linkage.GeneratedComparison:
    """Compare a generated GRE structure against the imported research corpus.

    Finds historical runs matching the generated structure's parameters
    and returns a detailed comparison including best match, average metrics,
    and evidence-chain linkage strength.

    Args:
        graph_nodes: Number of nodes in the generated fractal graph.
        depth: Circuit depth / recursion level.
        backend: Backend name.
        project: Optional project filter.
        fidelity: Observed fidelity of the generated structure.
        phi_deviation: Observed φ deviation.
        sierpinski_score: Observed Sierpinski score.
        route: Mathematical route used.
        corpus: Optional corpus. If None, uses the lazily-loaded global corpus.
        tolerance: Node-count tolerance for matching (default 10%).

    Returns:
        A :class:`GeneratedComparison` with matching records and evidence assessment.

    Example::

        comparison = compare_to_generated(
            corpus=corpus,
            graph_nodes=33,
            depth=3,
            backend="ibmq_qasm_simulator",
            fidelity=0.891,
        )
        print(f"Best match: {comparison.best_match_similarity:.3f}")
        print(f"Evidence for claims: {comparison.claim_supported}")
    """
    if corpus is None:
        corpus, _, linkage_instance = _ensure_loaded()
    else:
        _, _, linkage_instance = _ensure_loaded()

    linker = OutputLinker(corpus, linkage_instance)
    return linker.compare_generated_to_history(
        graph_nodes=graph_nodes,
        depth=depth,
        backend=backend,
        project=project,
        tolerance=tolerance,
        route=route,
        phi_deviation=phi_deviation,
        fidelity=fidelity,
        sierpinski_score=sierpinski_score,
    )


def get_claim(claim_id: str) -> Optional[ImportedClaimRecord]:
    """Retrieve a claim by ID from the loaded corpus.

    Args:
        claim_id: The claim identifier.

    Returns:
        ImportedClaimRecord if found, None otherwise.
    """
    _, _, linkage_instance = _ensure_loaded()
    return linkage_instance.get_claim(claim_id)


def evidence_chain(
    claim_id: str,
    corpus: Optional[ResearchCorpus] = None,
) -> Dict[str, Any]:
    """Build the full evidence chain for a claim.

    Returns the claim record, all supporting artifacts, and calibration context.

    Args:
        claim_id: ID of the claim to trace.
        corpus: Optional corpus. If None, uses the lazily-loaded global corpus.

    Returns:
        Dict with keys: ``claim``, ``supporting_artifacts``, ``calibration_context``,
        ``evidence_strength``.
    """
    if corpus is None:
        corpus, _, linkage_instance = _ensure_loaded()
    else:
        _, _, linkage_instance = _ensure_loaded()

    linker = OutputLinker(corpus, linkage_instance)
    return linker.build_evidence_chain(claim_id)


# -----------------------------------------------------------------------------
# Re-export everything for convenience
# -----------------------------------------------------------------------------

__all__ = [
    # Schemas
    "HardwareRunRecord",
    "SierpinskiExperimentRecord",
    "CalibrationSnapshot",
    "ProvenanceSidecar",
    "ArtifactDescriptor",
    "ExperimentMetadata",
    "ExperimentTag",
    "CircuitFamily",
    "BackendName",
    "EvidenceClass",
    "ValidationTier",
    "BackendGeneration",
    "CalibrationCompleteness",
    # Artifacts
    "ArtifactModel",
    "ArtifactRegistry",
    # Provenance
    "ProvenanceChain",
    "TransformStep",
    # Corpus
    "ResearchCorpus",
    "load_project_corpus",
    # Catalog & loader
    "CorpusCatalog",
    "CatalogEntry",
    "discover_imports_dir",
    "load_corpus",
    "LoadStats",
    # Calibration fetch
    "calibration_fetch",
    "infer_calibration_completeness",
    "has_physical_calibration_data",
    "parse_ibm_calibration_payload",
    "load_calibration_from_file",
    "upgrade_calibration_snapshot",
    "resolve_best_snapshot",
    "UpgradeResult",
    "CalibrationCompleteness",
    # Normalizers
    "normalizers",
    # Linkage
    "ImportedClaimRecord",
    "ClaimLinkage",
    "EvidenceLink",
    "OutputLinker",
    "GeneratedComparison",
    # Convenience queries
    "list_projects",
    "query_runs",
    "query_sierpinski",
    "compare_to_generated",
    "get_claim",
    "evidence_chain",
]
