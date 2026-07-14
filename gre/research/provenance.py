"""Provenance tracking for imported research artifacts.

Tracks the origin, transformation chain, and sensitivity classification
of every imported artifact. This is the sidecar model that travels with
each record and enables audit, reproducibility, and cross-project claims.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional


@dataclass
class TransformStep:
    """A single transformation step applied to an artifact.

    Attributes:
        step_id: Sequential ID for this step within the chain.
        transform_type: Type label for the transform (e.g., "normalize",
            "filter", "aggregate", "reformat", "validate").
        description: Human-readable description of what was done.
        parameters: Dict of parameters passed to the transform.
        timestamp: ISO-8601 timestamp when the transform was applied.
        tool: Tool or script name that applied the transform.
    """

    step_id: int
    transform_type: str
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    tool: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "transform_type": self.transform_type,
            "description": self.description,
            "parameters": self.parameters,
            "timestamp": self.timestamp or datetime.utcnow().isoformat() + "Z",
            "tool": self.tool,
        }


@dataclass
class ProvenanceSidecar:
    """Provenance metadata for a research artifact or record.

    Every imported or generated artifact carries this sidecar to track:
    - Where it came from (source_project, source_path, source_commit)
    - What was done to it (transform_chain)
    - What it claims to support (claims_supported)
    - How sensitive it is (sensitivity)

    This follows the PASS (Provenance, Authenticity, Scope, Sensitivity)
    framework for research data provenance.

    Attributes:
        source_project: Name of the originating project (e.g., "qsg",
            "sierpinski", "tmt").
        source_artifact_id: Artifact ID within the source project.
        source_path: Original file path or reference within source project.
        source_commit: Git commit hash in source project (if applicable).
        source_date: Date of the artifact in source project.
        backend: Backend used for this artifact (if applicable).
        import_date: ISO-8601 date when imported into GRE.
        import_method: How this was imported (e.g., "csv_import",
            "json_import", "manual_entry", "automated_scrape").
        sensitivity: Sensitivity level — "public", "internal", "restricted".
        transform_chain: Ordered list of TransformStep applied since import.
        claims_supported: List of claims this artifact supports.
        linked_files: Paths to related files in GRE storage.
        notes: Additional provenance notes.
    """

    source_project: str = ""
    source_artifact_id: str = ""
    source_path: str = ""
    source_commit: str = ""
    source_date: str = ""
    backend: str = ""
    import_date: str = ""
    import_method: str = ""
    sensitivity: str = "internal"
    import_type: str = "historical_real"  # "historical_real" | "synthetic_seed"
    transform_chain: List[TransformStep] = field(default_factory=list)
    claims_supported: List[str] = field(default_factory=list)
    linked_files: List[str] = field(default_factory=list)
    notes: str = ""

    def __post_init__(self):
        if not self.import_date:
            self.import_date = datetime.utcnow().isoformat() + "Z"

    def add_transform(
        self,
        transform_type: str,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        tool: str = ""
    ) -> None:
        """Append a transformation step to the chain."""
        step = TransformStep(
            step_id=len(self.transform_chain),
            transform_type=transform_type,
            description=description,
            parameters=parameters or {},
            timestamp=datetime.utcnow().isoformat() + "Z",
            tool=tool,
        )
        self.transform_chain.append(step)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_project": self.source_project,
            "source_artifact_id": self.source_artifact_id,
            "source_path": self.source_path,
            "source_commit": self.source_commit,
            "source_date": self.source_date,
            "backend": self.backend,
            "import_date": self.import_date,
            "import_method": self.import_method,
            "sensitivity": self.sensitivity,
            "import_type": self.import_type,
            "transform_chain": [s.to_dict() for s in self.transform_chain],
            "claims_supported": self.claims_supported,
            "linked_files": self.linked_files,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProvenanceSidecar":
        chain = [
            TransformStep(**s) for s in d.get("transform_chain", [])
        ]
        return cls(
            source_project=d.get("source_project", ""),
            source_artifact_id=d.get("source_artifact_id", ""),
            source_path=d.get("source_path", ""),
            source_commit=d.get("source_commit", ""),
            source_date=d.get("source_date", ""),
            backend=d.get("backend", ""),
            import_date=d.get("import_date", ""),
            import_method=d.get("import_method", ""),
            sensitivity=d.get("sensitivity", "internal"),
            import_type=d.get("import_type", "historical_real"),
            transform_chain=chain,
            claims_supported=d.get("claims_supported", []),
            linked_files=d.get("linked_files", []),
            notes=d.get("notes", ""),
        )

    def summary(self) -> str:
        """One-line provenance summary."""
        parts = [f"from={self.source_project}"]
        if self.source_path:
            parts.append(f"path={self.source_path}")
        if self.import_method:
            parts.append(f"via={self.import_method}")
        if self.transform_chain:
            parts.append(f"transforms={len(self.transform_chain)}")
        return " | ".join(parts)


@dataclass
class ProvenanceChain:
    """Full provenance chain for a record or artifact.

    This extends ProvenanceSidecar with the full chain representation
    used for audit and reproducibility reports.

    Attributes:
        sidecar: The ProvenanceSidecar for this artifact.
        parent_artifacts: List of artifact IDs that were inputs to this artifact.
        child_artifacts: List of artifact IDs derived from this artifact.
        validation_status: "validated", "unvalidated", "failed".
        validation_notes: Notes on validation checks performed.
    """

    sidecar: ProvenanceSidecar = field(default_factory=ProvenanceSidecar)
    parent_artifacts: List[str] = field(default_factory=list)
    child_artifacts: List[str] = field(default_factory=list)
    validation_status: str = "unvalidated"
    validation_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sidecar": self.sidecar.to_dict(),
            "parent_artifacts": self.parent_artifacts,
            "child_artifacts": self.child_artifacts,
            "validation_status": self.validation_status,
            "validation_notes": self.validation_notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProvenanceChain":
        sidecar = ProvenanceSidecar.from_dict(d.get("sidecar", {}))
        return cls(
            sidecar=sidecar,
            parent_artifacts=d.get("parent_artifacts", []),
            child_artifacts=d.get("child_artifacts", []),
            validation_status=d.get("validation_status", "unvalidated"),
            validation_notes=d.get("validation_notes", ""),
        )
