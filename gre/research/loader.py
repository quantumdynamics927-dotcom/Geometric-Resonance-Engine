"""Loading all imported artifacts into canonical GRE records.

The loader module consumes the corpus catalog and materializes
each artifact into its canonical schema: HardwareRunRecord,
SierpinskiExperimentRecord, CalibrationSnapshot, or ImportedClaimRecord.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from .catalog import CorpusCatalog, CatalogEntry, discover_imports_dir
from .schemas import (
    HardwareRunRecord,
    SierpinskiExperimentRecord,
    CalibrationSnapshot,
)
from .provenance import ProvenanceSidecar, TransformStep
from . import normalizers
from . import linkage


# -----------------------------------------------------------------------------
# Loader result
# -----------------------------------------------------------------------------

@dataclass
class LoadStats:
    """Statistics from a load operation."""
    total_entries: int = 0
    hardware_runs_loaded: int = 0
    sierpinski_experiments_loaded: int = 0
    calibrations_loaded: int = 0
    skipped: int = 0
    errors: int = 0
    error_messages: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_entries": self.total_entries,
            "hardware_runs_loaded": self.hardware_runs_loaded,
            "sierpinski_experiments_loaded": self.sierpinski_experiments_loaded,
            "calibrations_loaded": self.calibrations_loaded,
            "skipped": self.skipped,
            "errors": self.errors,
            "error_messages": self.error_messages,
        }


# -----------------------------------------------------------------------------
# CorpusLoader
# -----------------------------------------------------------------------------

class CorpusLoader:
    """Loads artifacts from the catalog into canonical GRE records.

    Given a CorpusCatalog and the imports/ directory, materializes each
    catalogued artifact into its typed record and populates the
    research corpus dicts.
    """

    def __init__(self, corpus: "ResearchCorpus", catalog: CorpusCatalog):
        self.corpus = corpus
        self.catalog = catalog

    def load_all(
        self,
        imports_dir: Path,
    ) -> LoadStats:
        """Load all catalogued artifacts.

        Args:
            imports_dir: Path to imports/ directory.

        Returns:
            LoadStats with counts and any errors.
        """
        stats = LoadStats(total_entries=len(self.catalog.entries))

        for entry in self.catalog.entries:
            try:
                loaded = self._load_entry(entry, imports_dir)
                if loaded:
                    if entry.artifact_type == "sierpinski_experiment":
                        stats.sierpinski_experiments_loaded += 1
                    elif entry.artifact_type == "calibration":
                        stats.calibrations_loaded += 1
                    else:
                        stats.hardware_runs_loaded += 1
                else:
                    stats.skipped += 1
            except Exception as exc:
                stats.errors += 1
                stats.error_messages.append(f"{entry.artifact_id}: {exc}")

        return stats

    def _load_entry(
        self,
        entry: CatalogEntry,
        imports_dir: Path,
    ) -> bool:
        """Load a single catalog entry.

        Returns True if loaded, False if skipped.
        """
        # Load provenance sidecar
        provenance = self._load_provenance(entry)

        # Load data
        data: Dict[str, Any] = {}
        if entry.data_path:
            data_path = Path(entry.data_path)
            if data_path.suffix == ".json":
                with open(data_path, encoding="utf-8") as f:
                    data = json.load(f)
            elif data_path.suffix == ".csv":
                import csv
                with open(data_path, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    if rows:
                        data = dict(rows[0])

        # Normalize
        result = normalizers.auto_normalize(
            data,
            provenance=provenance,
            source_project=entry.source_project,
        )

        # Store in corpus
        record = result.record

        if isinstance(record, SierpinskiExperimentRecord):
            self.corpus.sierpinski_experiments[record.hardware_record.metadata.experiment_id] = record
            self.corpus.hardware_runs[record.hardware_record.metadata.experiment_id] = record.hardware_record
        elif isinstance(record, CalibrationSnapshot):
            self.corpus.calibrations[record.snapshot_id] = record
        elif isinstance(record, HardwareRunRecord):
            self.corpus.hardware_runs[record.metadata.experiment_id] = record

        return True

    def _load_provenance(self, entry: CatalogEntry) -> ProvenanceSidecar:
        """Load provenance sidecar for an entry."""
        if entry.provenance_path and Path(entry.provenance_path).exists():
            with open(entry.provenance_path, encoding="utf-8") as f:
                d = json.load(f)
                return ProvenanceSidecar.from_dict(d)

        return ProvenanceSidecar(
            source_project=entry.source_project,
            source_artifact_id=entry.artifact_id,
            source_path=entry.source_path,
            import_date=entry.import_date,
            sensitivity=entry.sensitivity,
            claims_supported=entry.claims,
        )


# -----------------------------------------------------------------------------
# Module-level convenience functions
# -----------------------------------------------------------------------------

def load_corpus(
    imports_dir: Optional[Path] = None,
    catalog_path: Optional[Path] = None,
    skip_cache: bool = False,
) -> Tuple["ResearchCorpus", CorpusCatalog, LoadStats]:
    """Load the full research corpus.

    Convenience function that:
    1. Discovers all artifacts in imports_dir
    2. Loads them into a ResearchCorpus
    3. Returns (corpus, catalog, stats)

    Args:
        imports_dir: Path to imports/ directory.
            Defaults to gre/research/imports/ relative to this file.
        catalog_path: Optional path to pre-built catalog JSON.
        skip_cache: If True, ignore catalog_path and rebuild.

    Returns:
        Tuple of (ResearchCorpus, CorpusCatalog, LoadStats).
    """
    from .corpus import ResearchCorpus

    if imports_dir is None:
        imports_dir = Path(__file__).parent.parent.parent / "imports"

    # Try to load existing catalog
    if catalog_path is None:
        catalog_path = imports_dir / ".catalog.json"

    if not skip_cache and catalog_path.exists():
        try:
            catalog = CorpusCatalog.load(catalog_path)
        except (json.JSONDecodeError, IOError):
            catalog = discover_imports_dir(imports_dir)
            catalog.save(catalog_path)
    else:
        catalog = discover_imports_dir(imports_dir)
        catalog.save(catalog_path)

    corpus = ResearchCorpus()
    loader = CorpusLoader(corpus, catalog)
    stats = loader.load_all(imports_dir)

    return corpus, catalog, stats
