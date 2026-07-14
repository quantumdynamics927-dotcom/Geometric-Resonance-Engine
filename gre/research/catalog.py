"""Corpus discovery and indexing.

Scans import directories, discovers artifacts, and builds searchable indexes
over the research corpus.
"""

import json
import csv
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Iterator
from dataclasses import dataclass, field

from .schemas import (
    HardwareRunRecord,
    SierpinskiExperimentRecord,
    CalibrationSnapshot,
    ExperimentTag,
    CircuitFamily,
    BackendName,
)
from .provenance import ProvenanceSidecar


# -----------------------------------------------------------------------------
# Catalog entry
# -----------------------------------------------------------------------------

@dataclass
class CatalogEntry:
    """A single artifact indexed in the catalog."""
    artifact_id: str
    artifact_type: str  # "hardware_run" | "sierpinski_experiment" | "calibration"
    source_project: str
    source_path: str
    source_date: str
    import_date: str
    backend: str
    circuit_family: str
    depth: int
    shots: int
    sensitivity: str
    provenance_path: Optional[str] = None
    summary_path: Optional[str] = None
    data_path: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    claims: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "source_project": self.source_project,
            "source_path": self.source_path,
            "source_date": self.source_date,
            "import_date": self.import_date,
            "backend": self.backend,
            "circuit_family": self.circuit_family,
            "depth": self.depth,
            "shots": self.shots,
            "sensitivity": self.sensitivity,
            "provenance_path": self.provenance_path,
            "summary_path": self.summary_path,
            "data_path": self.data_path,
            "tags": self.tags,
            "claims": self.claims,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CatalogEntry":
        return cls(
            artifact_id=d["artifact_id"],
            artifact_type=d["artifact_type"],
            source_project=d.get("source_project", ""),
            source_path=d.get("source_path", ""),
            source_date=d.get("source_date", ""),
            import_date=d.get("import_date", ""),
            backend=d.get("backend", ""),
            circuit_family=d.get("circuit_family", ""),
            depth=d.get("depth", 0),
            shots=d.get("shots", 0),
            sensitivity=d.get("sensitivity", ""),
            provenance_path=d.get("provenance_path"),
            summary_path=d.get("summary_path"),
            data_path=d.get("data_path"),
            tags=d.get("tags", []),
            claims=d.get("claims", []),
        )


# -----------------------------------------------------------------------------
# CorpusCatalog
# -----------------------------------------------------------------------------

@dataclass
class CorpusCatalog:
    """Indexed inventory of all imported research artifacts.

    Built by scanning the imports/ directory. Provides fast lookups
    and filtered searches over the corpus.
    """
    entries: List[CatalogEntry] = field(default_factory=list)
    _by_project: Dict[str, List[CatalogEntry]] = field(default_factory=dict)
    _by_type: Dict[str, List[CatalogEntry]] = field(default_factory=dict)
    _by_backend: Dict[str, List[CatalogEntry]] = field(default_factory=dict)
    _by_claim: Dict[str, List[CatalogEntry]] = field(default_factory=dict)

    def build_index(self) -> None:
        """Rebuild fast lookup indexes."""
        self._by_project.clear()
        self._by_type.clear()
        self._by_backend.clear()
        self._by_claim.clear()

        for entry in self.entries:
            # By project
            if entry.source_project not in self._by_project:
                self._by_project[entry.source_project] = []
            self._by_project[entry.source_project].append(entry)

            # By type
            if entry.artifact_type not in self._by_type:
                self._by_type[entry.artifact_type] = []
            self._by_type[entry.artifact_type].append(entry)

            # By backend
            if entry.backend:
                if entry.backend not in self._by_backend:
                    self._by_backend[entry.backend] = []
                self._by_backend[entry.backend].append(entry)

            # By claim
            for claim in entry.claims:
                if claim not in self._by_claim:
                    self._by_claim[claim] = []
                self._by_claim[claim].append(entry)

    # -------------------------------------------------------------------------
    # Queries
    # -------------------------------------------------------------------------

    def projects(self) -> List[str]:
        """List all source projects in the catalog."""
        return list(self._by_project.keys())

    def by_project(self, project: str) -> List[CatalogEntry]:
        """Get all entries for a project."""
        return self._by_project.get(project, [])

    def by_type(self, artifact_type: str) -> List[CatalogEntry]:
        """Get all entries of a given type."""
        return self._by_type.get(artifact_type, [])

    def by_backend(self, backend: str) -> List[CatalogEntry]:
        """Get all entries for a backend."""
        return self._by_backend.get(backend, [])

    def by_claim(self, claim_id: str) -> List[CatalogEntry]:
        """Get all artifacts supporting a claim."""
        return self._by_claim.get(claim_id, [])

    def search(
        self,
        project: Optional[str] = None,
        artifact_type: Optional[str] = None,
        backend: Optional[str] = None,
        min_depth: Optional[int] = None,
        max_depth: Optional[int] = None,
        tag: Optional[str] = None,
        claim: Optional[str] = None,
    ) -> List[CatalogEntry]:
        """Multi-filtered search over catalog entries."""
        results = self.entries

        if project:
            results = [e for e in results if e.source_project == project]
        if artifact_type:
            results = [e for e in results if e.artifact_type == artifact_type]
        if backend:
            results = [e for e in results if e.backend == backend]
        if min_depth is not None:
            results = [e for e in results if e.depth >= min_depth]
        if max_depth is not None:
            results = [e for e in results if e.depth <= max_depth]
        if tag:
            results = [e for e in results if tag in e.tags]
        if claim:
            results = [e for e in results if claim in e.claims]

        return results

    def stats(self) -> Dict[str, Any]:
        """Summary statistics for the catalog."""
        return {
            "total_artifacts": len(self.entries),
            "by_type": {k: len(v) for k, v in self._by_type.items()},
            "by_project": {k: len(v) for k, v in self._by_project.items()},
            "by_backend": {k: len(v) for k, v in self._by_backend.items()},
            "unique_claims": len(self._by_claim),
        }

    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "indexed_at": datetime.utcnow().isoformat() + "Z",
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CorpusCatalog":
        catalog = cls(entries=[
            CatalogEntry.from_dict(e) for e in d.get("entries", [])
        ])
        catalog.build_index()
        return catalog

    def save(self, path: Path) -> None:
        """Save catalog to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path) -> "CorpusCatalog":
        """Load catalog from a JSON file."""
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


# -----------------------------------------------------------------------------
# Discovery
# -----------------------------------------------------------------------------

ARTIFACT_TYPE_PATTERNS: Dict[str, List[str]] = {
    "hardware_run": ["*.json", "*.csv"],
    "sierpinski_experiment": ["*.json", "*.csv", "*.md"],
    "calibration": ["*.json"],
}


def discover_imports_dir(imports_dir: Path) -> CorpusCatalog:
    """Scan the imports/ directory and build a catalog.

    Args:
        imports_dir: Path to the imports/ directory containing
            project subdirectories (qsg/, sierpinski/, calibration/).

    Returns:
        CorpusCatalog with all discovered artifacts.
    """
    catalog = CorpusCatalog()

    if not imports_dir.is_dir():
        return catalog

    for project_dir in sorted(imports_dir.iterdir()):
        if not project_dir.is_dir() or project_dir.name.startswith("_"):
            continue

        project_name = project_dir.name
        catalog.entries.extend(_scan_project_dir(project_dir, project_name))

    catalog.build_index()
    return catalog


def _scan_project_dir(project_dir: Path, project_name: str) -> List[CatalogEntry]:
    """Scan a single project directory (e.g. imports/sierpinski/)."""
    entries: List[CatalogEntry] = []

    for file_path in project_dir.iterdir():
        if file_path.is_file():
            entry = _discover_artifact(file_path, project_name)
            if entry:
                entries.append(entry)

    return entries


def _discover_artifact(file_path: Path, project_name: str) -> Optional[CatalogEntry]:
    """Discover a single artifact and its sidecars.

    Looks for:
    - data file (sierpinski-level5-ifs.json)
    - provenance sidecar (sierpinski-level5-ifs.provenance.json)
    - summary sidecar (sierpinski-level5-ifs.summary.md)
    """
    stem = file_path.stem
    suffix = file_path.suffix
    parent = file_path.parent

    # Only process primary data files (not sidecars)
    if ".provenance" in stem or ".summary" in stem:
        return None

    # Skip markdown files -- they are documentation sidecars, not primary data
    if suffix == ".md":
        return None

    # Determine artifact type from directory name and file
    artifact_type = _infer_artifact_type(parent.name, stem, suffix)

    # Locate sidecar files
    provenance_path = parent / f"{stem}.provenance.json"
    summary_path = parent / f"{stem}.summary.md"

    prov_data: Dict[str, Any] = {}
    if provenance_path.exists():
        try:
            with open(provenance_path, encoding="utf-8") as f:
                prov_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # Load summary for tags/claims if no provenance
    summary_data: Dict[str, Any] = {}
    if summary_path.exists():
        try:
            with open(summary_path, encoding="utf-8") as f:
                summary_data = _parse_summary_for_claims(f.read())
        except IOError:
            pass

    # Extract data from primary file
    data: Dict[str, Any] = {}
    if file_path.suffix == ".json":
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    elif file_path.suffix == ".csv":
        data = _parse_csv_record(file_path)

    artifact_id = prov_data.get("artifact_id") or data.get("experiment_id") or data.get("snapshot_id") or stem
    source_path = prov_data.get("source_path") or str(file_path)
    source_date = prov_data.get("source_date") or data.get("date") or data.get("timestamp") or ""
    import_date = prov_data.get("import_date") or datetime.utcnow().isoformat() + "Z"
    sensitivity = prov_data.get("sensitivity", "internal")

    backend = data.get("backend", "")
    depth = int(data.get("depth", data.get("recursion_level", 0)))
    shots = int(data.get("shots", 0))

    circuit_family = data.get("circuit_family", "")

    claims: List[str] = []
    claims.extend(prov_data.get("claims_supported", []))
    claims.extend(summary_data.get("claims", []))
    claims = list(dict.fromkeys(claims))  # deduplicate preserve order

    tags: List[str] = []
    if summary_path.exists():
        tags.extend(summary_data.get("tags", []))

    entry = CatalogEntry(
        artifact_id=str(artifact_id),
        artifact_type=artifact_type,
        source_project=project_name,
        source_path=source_path,
        source_date=source_date,
        import_date=import_date,
        backend=str(backend),
        circuit_family=circuit_family,
        depth=depth,
        shots=shots,
        sensitivity=sensitivity,
        provenance_path=str(provenance_path) if provenance_path.exists() else None,
        summary_path=str(summary_path) if summary_path.exists() else None,
        data_path=str(file_path),
        tags=tags,
        claims=claims,
    )

    return entry


def _infer_artifact_type(dir_name: str, stem: str, suffix: str) -> str:
    """Infer artifact type from directory name, file stem, and suffix."""
    # Directory-based inference
    if dir_name == "sierpinski":
        return "sierpinski_experiment"
    elif dir_name == "calibration":
        return "calibration"
    elif dir_name in ("qsg", "hardware"):
        return "hardware_run"

    # Stem-based inference
    if "sierpinski" in stem.lower() or "pascal" in stem.lower():
        return "sierpinski_experiment"
    if "cal" in stem.lower() and "ibm" in stem.lower():
        return "calibration"

    return "hardware_run"


def _parse_summary_for_claims(content: str) -> Dict[str, Any]:
    """Extract claims and tags from a summary Markdown file."""
    result: Dict[str, Any] = {"claims": [], "tags": []}

    # Look for ## Claims section
    claims_match = re.search(r"## Claims?\s*\n((?:[-*].*\n)+)", content)
    if claims_match:
        for line in claims_match.group(1).strip().split("\n"):
            line = line.lstrip("-* ").strip()
            if line:
                result["claims"].append(line)

    # Look for tag-like patterns: **Tag**: value or tags: [a, b]
    tag_matches = re.findall(r"\*\*?(?:tag|keyword)s?\*\*?:\s*\[?(.*?)\]?", content, re.IGNORECASE)
    for tag_line in tag_matches:
        for tag in re.split(r"[,\s]+", tag_line):
            tag = tag.strip().strip("'\"").strip("*")
            if tag and len(tag) > 1:
                result["tags"].append(tag)

    return result


def _parse_csv_record(file_path: Path) -> Dict[str, Any]:
    """Parse a CSV file into a dict (first row = headers)."""
    try:
        with open(file_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if rows:
                return dict(rows[0])
    except (csv.Error, IOError):
        pass
    return {}
