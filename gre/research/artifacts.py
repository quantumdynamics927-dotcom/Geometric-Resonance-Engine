"""Artifact registry and artifact model for research data.

Artifacts are the raw or processed data files that underly experiments.
Each artifact is registered with its descriptor and stored path so that
records can reference them without duplicating data.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional
import hashlib
import json
import os
from pathlib import Path

from .schemas import ArtifactDescriptor, ProvenanceSidecar


@dataclass
class ArtifactModel:
    """A single research artifact.

    Artifacts are the raw or derived data files that underly experiments.
    They are identified by content hash (SHA-256) and carry provenance
    and descriptor metadata.

    Attributes:
        artifact_id: Unique identifier (e.g., "artifact-00123").
        descriptor: ArtifactDescriptor with origin metadata.
        provenance: ProvenanceSidecar tracking transformation history.
        storage_path: Absolute path to the artifact file in GRE storage.
        content_hash: SHA-256 of the artifact content.
        size_bytes: Size of the artifact in bytes.
        artifact_type: File extension/type (e.g., "csv", "json", "qasm", "png").
        metadata: Arbitrary additional metadata.
        created_at: ISO-8601 creation timestamp.
    """

    artifact_id: str
    descriptor: ArtifactDescriptor
    provenance: ProvenanceSidecar = field(default_factory=ProvenanceSidecar)
    storage_path: str = ""
    content_hash: str = ""
    size_bytes: int = 0
    artifact_type: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"
        if not self.artifact_type and self.storage_path:
            self.artifact_type = os.path.splitext(self.storage_path)[1].lstrip(".")

    def compute_hash(self, data: bytes) -> str:
        """Compute SHA-256 hash of artifact content."""
        return hashlib.sha256(data).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "descriptor": self.descriptor.to_dict(),
            "provenance": self.provenance.to_dict(),
            "storage_path": self.storage_path,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "artifact_type": self.artifact_type,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ArtifactModel":
        descriptor = ArtifactDescriptor(**d["descriptor"])
        provenance = ProvenanceSidecar.from_dict(d.get("provenance", {}))
        return cls(
            artifact_id=d["artifact_id"],
            descriptor=descriptor,
            provenance=provenance,
            storage_path=d.get("storage_path", ""),
            content_hash=d.get("content_hash", ""),
            size_bytes=d.get("size_bytes", 0),
            artifact_type=d.get("artifact_type", ""),
            metadata=d.get("metadata", {}),
            created_at=d.get("created_at", ""),
        )


class ArtifactRegistry:
    """Registry of all known artifacts.

    Maintains a manifest of artifact IDs → ArtifactModel instances,
    with optional disk-backed storage for the registry itself.

    Usage:
        registry = ArtifactRegistry()
        registry.register(my_artifact)
        artifact = registry.get("artifact-00123")
        manifest = registry.list_by_project("qsg")
        registry.save("artifacts.json")

    Artifacts themselves are stored at their `storage_path`;
    the registry only tracks metadata and provenance.
    """

    def __init__(self):
        self._artifacts: Dict[str, ArtifactModel] = {}

    def register(self, artifact: ArtifactModel) -> None:
        """Register an artifact in the registry."""
        self._artifacts[artifact.artifact_id] = artifact

    def get(self, artifact_id: str) -> Optional[ArtifactModel]:
        """Get an artifact by ID."""
        return self._artifacts.get(artifact_id)

    def list_all(self) -> List[ArtifactModel]:
        """List all registered artifacts."""
        return list(self._artifacts.values())

    def list_by_project(self, project: str) -> List[ArtifactModel]:
        """List artifacts from a specific source project."""
        return [
            a for a in self._artifacts.values()
            if a.descriptor.source_project == project
        ]

    def list_by_type(self, artifact_type: str) -> List[ArtifactModel]:
        """List artifacts of a specific type."""
        return [
            a for a in self._artifacts.values()
            if a.artifact_type == artifact_type
        ]

    def list_by_sensitivity(self, sensitivity: str) -> List[ArtifactModel]:
        """List artifacts by sensitivity level."""
        return [
            a for a in self._artifacts.values()
            if a.provenance.sensitivity == sensitivity
        ]

    def save(self, path: str) -> None:
        """Save registry manifest to JSON."""
        data = [a.to_dict() for a in self._artifacts.values()]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str) -> None:
        """Load registry manifest from JSON."""
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for d in data:
            artifact = ArtifactModel.from_dict(d)
            self._artifacts[artifact.artifact_id] = artifact

    def to_manifest_csv(self) -> str:
        """Generate a MANDATE-style manifest CSV."""
        lines = [
            "artifact_id,source_project,source_path,source_commit,"
            "artifact_type,sensitivity,storage_path,content_hash,"
            "created_at,import_date"
        ]
        for a in self._artifacts.values():
            d = a.descriptor
            p = a.provenance
            lines.append(
                f"{a.artifact_id},"
                f"{d.source_project},"
                f"{d.source_path},"
                f"{d.source_commit},"
                f"{a.artifact_type},"
                f"{p.sensitivity},"
                f"{a.storage_path},"
                f"{a.content_hash},"
                f"{a.created_at},"
                f"{p.import_date}"
            )
        return "\n".join(lines)
