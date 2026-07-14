"""Linkage between imported artifacts, claims, and GRE outputs.

This module maps:
1. Imported artifacts → claims they support
2. Imported artifacts → source experiments
3. Generated GRE outputs → nearest imported historical records
4. Claims → evidence chain (which artifacts back which claims)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set

from .schemas import (
    HardwareRunRecord,
    SierpinskiExperimentRecord,
    CalibrationSnapshot,
    ExperimentTag,
    ArtifactDescriptor,
)
from .provenance import ProvenanceSidecar


# -----------------------------------------------------------------------------
# ImportedClaimRecord
# -----------------------------------------------------------------------------

@dataclass
class ImportedClaimRecord:
    """A scientific claim supported by one or more imported artifacts.

    Claims are the interpretative layer on top of raw experimental data.
    Each claim is backed by a chain of evidence from imported artifacts.

    Attributes:
        claim_id: Unique identifier for this claim.
        claim_type: One of the ExperimentTag values.
        description: Human-readable description of the claim.
        hypothesis: The specific hypothesis being made.
        evidence: List of experiment IDs that support this claim.
        confidence: Confidence level (0.0 to 1.0).
        source_artifacts: IDs of imported artifacts providing evidence.
        calibration_context: IDs of calibration snapshots relevant to this claim.
        notes: Additional notes on the claim.
        provenance: ProvenanceSidecar for this claim record.
    """

    claim_id: str
    claim_type: ExperimentTag
    description: str
    hypothesis: str
    evidence: List[str] = field(default_factory=list)  # experiment IDs
    confidence: float = 0.0
    source_artifacts: List[str] = field(default_factory=list)
    calibration_context: List[str] = field(default_factory=list)
    notes: str = ""
    provenance: ProvenanceSidecar = field(default_factory=ProvenanceSidecar)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_type": self.claim_type.value,
            "description": self.description,
            "hypothesis": self.hypothesis,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "source_artifacts": self.source_artifacts,
            "calibration_context": self.calibration_context,
            "notes": self.notes,
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ImportedClaimRecord":
        provenance = ProvenanceSidecar.from_dict(d.get("provenance", {}))
        return cls(
            claim_id=d["claim_id"],
            claim_type=ExperimentTag(d.get("claim_type", "other")),
            description=d.get("description", ""),
            hypothesis=d.get("hypothesis", ""),
            evidence=d.get("evidence", []),
            confidence=d.get("confidence", 0.0),
            source_artifacts=d.get("source_artifacts", []),
            calibration_context=d.get("calibration_context", []),
            notes=d.get("notes", ""),
            provenance=provenance,
        )


# -----------------------------------------------------------------------------
# Claim evidence registry
# -----------------------------------------------------------------------------

@dataclass
class EvidenceLink:
    """A link between an artifact and a claim it supports."""
    claim_id: str
    artifact_id: str
    strength: float = 1.0  # 0.0 to 1.0
    provenance_chain: List[str] = field(default_factory=list)


class ClaimLinkage:
    """Registry linking imported artifacts to claims.

    Maintains the evidence graph:
    - artifact_id → set of claim_ids it supports
    - claim_id → set of artifact_ids providing evidence
    """

    def __init__(self):
        # artifact_id → set of claim_ids
        self._artifact_to_claims: Dict[str, Set[str]] = {}
        # claim_id → set of artifact_ids
        self._claim_to_artifacts: Dict[str, Set[str]] = {}
        # claim_id → ImportedClaimRecord
        self._claims: Dict[str, ImportedClaimRecord] = {}

    def register_claim(self, claim: ImportedClaimRecord) -> None:
        """Register a new claim."""
        self._claims[claim.claim_id] = claim
        if claim.claim_id not in self._claim_to_artifacts:
            self._claim_to_artifacts[claim.claim_id] = set()
        for artifact_id in claim.source_artifacts:
            self.link_artifact_to_claim(artifact_id, claim.claim_id)

    def link_artifact_to_claim(
        self,
        artifact_id: str,
        claim_id: str,
        strength: float = 1.0,
    ) -> None:
        """Link an artifact to a claim it supports."""
        if artifact_id not in self._artifact_to_claims:
            self._artifact_to_claims[artifact_id] = set()
        self._artifact_to_claims[artifact_id].add(claim_id)

        if claim_id not in self._claim_to_artifacts:
            self._claim_to_artifacts[claim_id] = set()
        self._claim_to_artifacts[claim_id].add(artifact_id)

    def claims_for_artifact(self, artifact_id: str) -> List[str]:
        """Get all claims supported by an artifact."""
        return list(self._artifact_to_claims.get(artifact_id, set()))

    def artifacts_for_claim(self, claim_id: str) -> List[str]:
        """Get all artifacts supporting a claim."""
        return list(self._claim_to_artifacts.get(claim_id, set()))

    def get_claim(self, claim_id: str) -> Optional[ImportedClaimRecord]:
        """Get a claim by ID."""
        return self._claims.get(claim_id)

    def all_claims(self) -> List[ImportedClaimRecord]:
        """Get all registered claims."""
        return list(self._claims.values())

    def claims_by_type(self, claim_type: ExperimentTag) -> List[ImportedClaimRecord]:
        """Get all claims of a specific type."""
        return [
            c for c in self._claims.values()
            if c.claim_type == claim_type
        ]


# -----------------------------------------------------------------------------
# Generated-to-historical linkage
# -----------------------------------------------------------------------------

@dataclass
class GeneratedComparison:
    """Result of comparing a generated GRE output against historical records.

    Attributes:
        generated_descriptor: Description of the generated structure.
        matching_records: Historical records matching this generation.
        avg_fidelity: Average fidelity across matches.
        avg_phi_deviation: Average phi_deviation across matches.
        best_match: Best-matching historical record.
        best_match_similarity: Similarity score for best match.
        claim_supported: Claims this comparison provides evidence for.
        linkage_strength: Overall strength of evidence chain.
    """

    generated_descriptor: Dict[str, Any]
    matching_records: List[HardwareRunRecord] = field(default_factory=list)
    avg_fidelity: Optional[float] = None
    avg_phi_deviation: Optional[float] = None
    best_match: Optional[HardwareRunRecord] = None
    best_match_similarity: Optional[float] = None
    claim_supported: List[str] = field(default_factory=list)
    linkage_strength: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_descriptor": self.generated_descriptor,
            "matching_records": [r.to_dict() for r in self.matching_records],
            "avg_fidelity": self.avg_fidelity,
            "avg_phi_deviation": self.avg_phi_deviation,
            "best_match": self.best_match.to_dict() if self.best_match else None,
            "best_match_similarity": self.best_match_similarity,
            "claim_supported": self.claim_supported,
            "linkage_strength": self.linkage_strength,
        }


class OutputLinker:
    """Links generated GRE outputs to imported historical records and claims.

    This is the core comparison engine for bridging generated structures
    against empirical evidence from prior projects.
    """

    def __init__(self, corpus: "ResearchCorpus", linkage: ClaimLinkage):
        self.corpus = corpus
        self.linkage = linkage

    def compare_generated_to_history(
        self,
        graph_nodes: int,
        depth: int,
        backend: str,
        project: Optional[str] = None,
        tolerance: float = 0.1,
        route: str = "ifs",
        phi_deviation: Optional[float] = None,
        fidelity: Optional[float] = None,
        sierpinski_score: Optional[float] = None,
    ) -> GeneratedComparison:
        """Compare a generated structure against historical hardware runs.

        Args:
            graph_nodes: Number of nodes in generated fractal graph.
            depth: Circuit depth / recursion level.
            backend: Backend name.
            project: Optional project filter.
            tolerance: Node count tolerance for matching.
            route: Mathematical route used.
            phi_deviation: Observed phi deviation (if available).
            fidelity: Observed fidelity (if available).
            sierpinski_score: Observed sierpinski_score (if available).

        Returns:
            GeneratedComparison with matching records and evidence assessment.
        """
        # Find matching historical runs
        matches = self.corpus.find_runs(
            depth=depth,
            backend=backend,
            project=project,
        )

        # Filter by node tolerance
        node_low = graph_nodes * (1 - tolerance)
        node_high = graph_nodes * (1 + tolerance)
        filtered = [
            r for r in matches
            if node_low <= r.qubit_count <= node_high
        ]

        if not filtered:
            return GeneratedComparison(
                generated_descriptor={
                    "graph_nodes": graph_nodes,
                    "depth": depth,
                    "backend": backend,
                    "route": route,
                    "phi_deviation": phi_deviation,
                    "fidelity": fidelity,
                    "sierpinski_score": sierpinski_score,
                }
            )

        # Compute aggregate metrics
        fidelities = [r.fidelity for r in filtered if r.fidelity is not None]
        phi_devs = [r.phi_deviation for r in filtered if r.phi_deviation is not None]
        scores = [r.sierpinski_score for r in filtered if r.sierpinski_score is not None]

        avg_fidelity = sum(fidelities) / len(fidelities) if fidelities else None
        avg_phi_deviation = sum(phi_devs) / len(phi_devs) if phi_devs else None
        avg_score = sum(scores) / len(scores) if scores else None

        # Best match
        if filtered:
            best = max(filtered, key=lambda r: r.fidelity or 0.0)

            # Compute similarity
            sim = 1.0
            if fidelity is not None and best.fidelity is not None:
                sim *= 1 - abs(fidelity - best.fidelity)
            if phi_deviation is not None and best.phi_deviation is not None:
                sim *= 1 - min(abs(phi_deviation - best.phi_deviation) / 0.01, 1.0)

            best_match_similarity = max(0.0, sim)
        else:
            best = None
            best_match_similarity = None

        # Determine which claims are supported
        claim_ids = set()
        for r in filtered:
            for aid in [r.metadata.experiment_id]:
                for cid in self.linkage.claims_for_artifact(aid):
                    claim_ids.add(cid)

        # Compute linkage strength
        linkage_strength = min(1.0, len(filtered) / 5) if filtered else 0.0

        return GeneratedComparison(
            generated_descriptor={
                "graph_nodes": graph_nodes,
                "depth": depth,
                "backend": backend,
                "route": route,
                "phi_deviation": phi_deviation,
                "fidelity": fidelity,
                "sierpinski_score": sierpinski_score,
            },
            matching_records=filtered,
            avg_fidelity=avg_fidelity,
            avg_phi_deviation=avg_phi_deviation,
            best_match=best,
            best_match_similarity=best_match_similarity,
            claim_supported=list(claim_ids),
            linkage_strength=linkage_strength,
        )

    def compare_sierpinski_fixed_point(
        self,
        observed_value: float,
        expected_value: float = 0.6180339887,
        tolerance: float = 0.05,
    ) -> Dict[str, Any]:
        """Compare observed fixed point against 1/φ and historical runs.

        Args:
            observed_value: Observed fixed-point value.
            expected_value: Expected value (default 1/φ).
            tolerance: Fractional tolerance for "consistent" classification.

        Returns:
            Dict with comparison results and claim assessment.
        """
        abs_error = abs(observed_value - expected_value)
        rel_error = abs_error / expected_value

        # Find runs with fixed point measurements
        sierpinski_runs = self.corpus.find_sierpinski_experiments()
        fp_runs = [
            r for r in sierpinski_runs
            if r.depth_invariant_fixed_point is not None
        ]

        consistent_with_theory = abs_error < tolerance * expected_value
        historical_values = [r.depth_invariant_fixed_point for r in fp_runs]
        historical_errors = [
            abs(fp - expected_value) / expected_value
            for fp in historical_values
        ]

        avg_historical_error = (
            sum(historical_errors) / len(historical_errors)
            if historical_errors else None
        )

        return {
            "observed": observed_value,
            "expected": expected_value,
            "absolute_error": abs_error,
            "relative_error": rel_error,
            "consistent_with_theory": consistent_with_theory,
            "consistent_with_history": (
                avg_historical_error is not None
                and rel_error < avg_historical_error * 1.5
            ),
            "historical_run_count": len(fp_runs),
            "avg_historical_error": avg_historical_error,
            "within_1pct": abs_error < 0.01 * expected_value,
            "within_5pct": abs_error < 0.05 * expected_value,
        }

    def build_evidence_chain(
        self,
        claim_id: str,
    ) -> Dict[str, Any]:
        """Build a complete evidence chain for a claim.

        Args:
            claim_id: ID of the claim.

        Returns:
            Dict with claim, supporting artifacts, and calibration context.
        """
        claim = self.linkage.get_claim(claim_id)
        if not claim:
            return {"error": f"Claim {claim_id} not found"}

        artifact_ids = self.linkage.artifacts_for_claim(claim_id)
        artifacts = []
        for aid in artifact_ids:
            run = self.corpus.hardware_runs.get(aid)
            if run:
                artifacts.append(run.to_dict())

        calibrations = []
        for cal_id in claim.calibration_context:
            cal = self.corpus.calibrations.get(cal_id)
            if cal:
                calibrations.append(cal.to_dict())

        return {
            "claim": claim.to_dict(),
            "supporting_artifacts": artifacts,
            "calibration_context": calibrations,
            "evidence_strength": len(artifacts),
        }
