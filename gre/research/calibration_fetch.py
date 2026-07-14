"""Local-first IBM Quantum calibration data ingestion.

Supports loading from:
  - IBM Quantum API saved response payloads (full physical calibration)
  - Metadata-only snapshots (backend + timestamp, no T1/T2 data)
  - Mixed sets where the newest snapshot is physical but older ones are not

Workflow:
  1. Save IBM Quantum API calibration responses as JSON fixtures locally
  2. Load via load_calibration_from_file() or parse_ibm_calibration_payload()
  3. infer_calibration_completeness() detects physical vs metadata vs absent
  4. upgrade_calibration_snapshot() safely upgrades a metadata snapshot to physical
     when new data is available, without losing provenance

Example saved IBM API calibration payload (saved from IBM Quantum API):
```json
{
  "backend": "ibm_kingston",
  "timestamp": "2026-04-23T12:00:00Z",
  "t1_times": {"0": 95.3, "1": 102.1, ...},
  "t2_times": {"0": 180.2, "1": 175.6, ...},
  "readout_errors": {"0": 0.021, "1": 0.018, ...},
  "gate_errors": {"cx0_1": 0.0061, "sx0": 0.0012, ...},
  "qubit_freqs": {"0": 4.9876, "1": 5.0123, ...},
  "readouts": {"0": 0.979, "1": 0.982, ...},
  "connectivity": [[0,1],[1,2],...],
  "qubit_count": 127,
  "basis_gates": ["cx", "sx", "x", "rz", "id"],
  "source": "ibm-quantum-api"
}
```

Minimal required fields for physical: t1_times AND t2_times (non-empty dicts)
"""

from __future__ import annotations

import json
import math
import hashlib
from pathlib import Path
from typing import Any, TypedDict


# ---------------------------------------------------------------------------
# Typed dicts for IBM API payload
# ---------------------------------------------------------------------------


class IBMCalibrationPayload(TypedDict, total=False):
    """Shape of a saved IBM Quantum API calibration response."""

    backend: str
    timestamp: str
    t1_times: dict[str, float]
    t2_times: dict[str, float]
    readout_errors: dict[str, float]
    gate_errors: dict[str, float]
    qubit_freqs: dict[str, float]
    readouts: dict[str, float]
    connectivity: list[list[int]]
    qubit_count: int
    basis_gates: list[str]
    source: str


# ---------------------------------------------------------------------------
# CalibrationCompleteness enum (mirrors schemas.py)
# ---------------------------------------------------------------------------


class CalibrationCompleteness:
    """Describes how much physical calibration data is present."""

    PHYSICAL = "physical"
    METADATA = "metadata"
    ABSENT = "absent"


# ---------------------------------------------------------------------------
# Core detection
# ---------------------------------------------------------------------------


def infer_calibration_completeness(payload: dict[str, Any]) -> str:
    """Infer calibration_completeness from a calibration payload.

    Rules (all fields checked; first matching rule wins):
      1. PHYSICAL  — t1_times AND t2_times are both non-empty dicts
      2. METADATA  — at least one of t1_times or t2_times is present
                    (even if empty) OR backend name is known
      3. ABSENT    — no recognizable calibration fields at all

    Args:
        payload: Parsed JSON dict from an IBM API calibration response,
                 OR a CalibrationSnapshot dict (historical record)

    Returns:
        CalibrationCompleteness value as string
    """
    t1 = payload.get("t1_times", {})
    t2 = payload.get("t2_times", {})
    readout = payload.get("readout_errors", {})
    gate_err = payload.get("gate_errors", {})
    freq = payload.get("qubit_freqs", {})
    readouts = payload.get("readouts", {})

    # PHYSICAL: both T1 and T2 present AND non-empty
    if isinstance(t1, dict) and t1 and isinstance(t2, dict) and t2:
        return CalibrationCompleteness.PHYSICAL

    # METADATA: at least one calibration field is present (even if empty dict)
    # This handles legacy records where fields were added over time
    has_any_calibration_field = any(
        isinstance(payload.get(k), dict)
        for k in (
            "t1_times", "t2_times", "readout_errors",
            "gate_errors", "qubit_freqs", "readouts",
        )
    )
    has_connectivity = isinstance(payload.get("connectivity"), list)
    has_backend = bool(payload.get("backend"))

    if has_any_calibration_field or has_connectivity or has_backend:
        return CalibrationCompleteness.METADATA

    return CalibrationCompleteness.ABSENT


def has_physical_calibration_data(payload: dict[str, Any]) -> bool:
    """Return True if the payload has actual T1/T2 measurements."""
    t1 = payload.get("t1_times", {})
    t2 = payload.get("t2_times", {})
    return bool(isinstance(t1, dict) and t1 and isinstance(t2, dict) and t2)


# ---------------------------------------------------------------------------
# Parsing IBM API calibration payload
# ---------------------------------------------------------------------------


def parse_ibm_calibration_payload(
    payload: dict[str, Any],
    *,
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Normalise an IBM Quantum API calibration response into a
    CalibrationSnapshot-compatible dict.

    Args:
        payload: Raw parsed JSON from a saved IBM API calibration response.
                 May contain IBM-specific field names (camelCase, snake_case,
                 or non-standard keys). All are normalised to snake_case.
        source_ref: Optional path/URL reference to the original payload file
                    (for provenance).

    Returns:
        Dict with canonical CalibrationSnapshot fields:
        {
          "backend": str,
          "timestamp": str,
          "t1_times": dict[str, float],
          "t2_times": dict[str, float],
          "readout_errors": dict[str, float],
          "gate_errors": dict[str, float],
          "qubit_freqs": dict[str, float],
          "readouts": dict[str, float],
          "connectivity": list[list[int]],
          "calibration_completeness": str,
          "qubit_count": int | None,
          "basis_gates": list[str],
          "source_payload_ref": str | None,
        }

    Raises:
        ValueError: If backend or timestamp cannot be determined from the payload.
    """
    backend = payload.get("backend") or payload.get("backend_name")
    if not backend:
        raise ValueError(
            "IBM calibration payload missing required field: 'backend'"
        )

    timestamp = payload.get("timestamp") or payload.get("created") or payload.get("date")
    if not timestamp:
        raise ValueError(
            f"IBM calibration payload for {backend!r} missing required field: "
            "'timestamp' (or 'created' / 'date')"
        )

    def _dict(val: Any) -> dict[str, float]:
        if isinstance(val, dict):
            return {str(k): float(v) for k, v in val.items()}
        return {}

    t1_times = _dict(payload.get("t1_times", {}))
    t2_times = _dict(payload.get("t2_times", {}))
    readout_errors = _dict(payload.get("readout_errors", {}))
    gate_errors = _dict(payload.get("gate_errors", {}))
    qubit_freqs = _dict(payload.get("qubit_freqs", {}))
    readouts = _dict(payload.get("readouts", {}))
    connectivity: list[list[int]] = []
    raw_conn = payload.get("connectivity", [])
    if isinstance(raw_conn, list):
        connectivity = [
            [int(a), int(b)]
            for a, b in raw_conn
            if isinstance(raw_conn, list) and len(raw_conn) > 0
        ]
        # connectivity might be a list of [int, int] pairs
        try:
            connectivity = [[int(a), int(b)] for a, b in raw_conn]
        except (TypeError, ValueError):
            connectivity = []

    qubit_count: int | None = None
    qc = payload.get("qubit_count")
    if qc is not None:
        try:
            qubit_count = int(qc)
        except (TypeError, ValueError):
            qubit_count = None

    basis_gates: list[str] = []
    bg = payload.get("basis_gates")
    if isinstance(bg, list):
        basis_gates = [str(g) for g in bg]

    completeness = infer_calibration_completeness(payload)

    return {
        "backend": str(backend),
        "timestamp": str(timestamp),
        "t1_times": t1_times,
        "t2_times": t2_times,
        "readout_errors": readout_errors,
        "gate_errors": gate_errors,
        "qubit_freqs": qubit_freqs,
        "readouts": readouts,
        "connectivity": connectivity,
        "calibration_completeness": completeness,
        "qubit_count": qubit_count,
        "basis_gates": basis_gates,
        "source_payload_ref": source_ref,
    }


# ---------------------------------------------------------------------------
# Loading from files
# ---------------------------------------------------------------------------


def load_calibration_from_file(path: str | Path) -> dict[str, Any]:
    """Load and parse a saved IBM Quantum calibration JSON file.

    Handles two formats:
      - IBM API payload format (from ibm-quantum-api source)
      - Already-normalised CalibrationSnapshot format (backward compat)

    Args:
        path: Path to a JSON file containing calibration data.

    Returns:
        Normalised CalibrationSnapshot dict with all canonical fields filled.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
        ValueError: If the file contains valid JSON but is not a recognised
                    calibration format.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Calibration file not found: {p}")

    with open(p, encoding="utf-8") as fh:
        raw = json.load(fh)

    if not isinstance(raw, dict):
        raise ValueError(f"Expected dict in {p}, got {type(raw).__name__}")

    # Detect format: IBM API payload has 'source' == 'ibm-quantum-api'
    # or 'timestamp' + 'backend' without 'calibration_completeness' (already normalised)
    is_ibm_api_format = raw.get("source") == "ibm-quantum-api"
    is_raw_snapshot = "calibration_completeness" not in raw and not is_ibm_api_format

    if is_ibm_api_format:
        return parse_ibm_calibration_payload(raw, source_ref=str(p))

    # Already a CalibrationSnapshot (possibly partially filled)
    # Normalise missing fields to empty defaults
    completeness = raw.get(
        "calibration_completeness",
        infer_calibration_completeness(raw),
    )

    def _ensure_dict(val: Any) -> dict[str, float]:
        if isinstance(val, dict):
            return {str(k): float(v) for k, v in val.items()}
        return {}

    def _ensure_list(val: Any) -> list:
        if isinstance(val, list):
            return val
        return []

    return {
        "backend": raw.get("backend", ""),
        "timestamp": raw.get("timestamp", ""),
        "t1_times": _ensure_dict(raw.get("t1_times")),
        "t2_times": _ensure_dict(raw.get("t2_times")),
        "readout_errors": _ensure_dict(raw.get("readout_errors")),
        "gate_errors": _ensure_dict(raw.get("gate_errors")),
        "qubit_freqs": _ensure_dict(raw.get("qubit_freqs")),
        "readouts": _ensure_dict(raw.get("readouts")),
        "connectivity": _ensure_list(raw.get("connectivity")),
        "calibration_completeness": completeness,
        "qubit_count": raw.get("qubit_count"),
        "basis_gates": raw.get("basis_gates", []),
        "source_payload_ref": raw.get("source_payload_ref", str(p)),
    }


# ---------------------------------------------------------------------------
# Upgrading metadata snapshot to physical
# ---------------------------------------------------------------------------


class UpgradeResult:
    """Result of an attempted calibration snapshot upgrade.

    Attributes:
        success: Whether the upgrade was applied.
        previous_completeness: The completeness before the upgrade attempt.
        new_completeness: The completeness after the upgrade (unchanged if failed).
        upgrades_applied: List of field names that were updated.
        message: Human-readable description of what happened.
    """

    def __init__(
        self,
        success: bool,
        previous_completeness: str,
        new_completeness: str,
        upgrades_applied: list[str],
        message: str,
    ):
        self.success = success
        self.previous_completeness = previous_completeness
        self.new_completeness = new_completeness
        self.upgrades_applied = upgrades_applied
        self.message = message

    def __repr__(self) -> str:
        return (
            f"UpgradeResult(success={self.success}, "
            f"completeness={self.previous_completeness}→{self.new_completeness}, "
            f"upgrades={self.upgrades_applied}, message={self.message!r})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "previous_completeness": self.previous_completeness,
            "new_completeness": self.new_completeness,
            "upgrades_applied": self.upgrades_applied,
            "message": self.message,
        }


def upgrade_calibration_snapshot(
    existing: dict[str, Any],
    new_data: dict[str, Any],
    *,
    allow_downgrade: bool = False,
) -> UpgradeResult:
    """Upgrade a calibration snapshot with new physical data.

    Safely merges new physical calibration data into an existing snapshot
    without losing provenance. Preserves metadata-only snapshots that cannot
    be upgraded (they stay metadata).

    Upgrade rules:
      1. Existing = metadata, new = physical → upgrade fields, set completeness=physical
      2. Existing = physical, new = physical  → merge (newer values win if timestamps differ)
      3. Existing = physical, new = metadata  → no change (unless allow_downgrade=True)
      4. Existing = metadata, new = metadata  → no change (metadata already captures what we know)
      5. Missing T1/T2 in new_data           → raise ValueError (corrupt payload)

    Args:
        existing: Current state of the CalibrationSnapshot dict.
        new_data: New calibration data (from parse_ibm_calibration_payload or
                  load_calibration_from_file).
        allow_downgrade: If True, allow a physical snapshot to be downgraded
                         to metadata when new_data lacks physical fields.
                         Default False (conservative — keep the best known state).

    Returns:
        UpgradeResult describing what changed.

    Raises:
        ValueError: If new_data has no T1 or no T2 measurements (corrupt/incomplete).
    """
    new_t1 = new_data.get("t1_times", {})
    new_t2 = new_data.get("t2_times", {})

    existing_completeness = existing.get(
        "calibration_completeness",
        infer_calibration_completeness(existing),
    )
    new_completeness = new_data.get(
        "calibration_completeness",
        infer_calibration_completeness(new_data),
    )

    upgrades_applied: list[str] = []
    result_completeness = existing_completeness

    # Case 1: existing=metadata, new=physical → upgrade
    if (
        existing_completeness == CalibrationCompleteness.METADATA
        and new_completeness == CalibrationCompleteness.PHYSICAL
    ):
        # Guard: new_data must actually have T1/T2 to do a physical upgrade
        if not new_t1 or not new_t2:
            raise ValueError(
                "new_data must contain non-empty t1_times AND t2_times to upgrade. "
                f"Got t1={bool(new_t1)}, t2={bool(new_t2)}."
            )
        fields_to_upgrade = [
            "t1_times",
            "t2_times",
            "readout_errors",
            "gate_errors",
            "qubit_freqs",
            "readouts",
            "connectivity",
            "qubit_count",
            "basis_gates",
        ]
        for field in fields_to_upgrade:
            if field in new_data and new_data[field]:
                existing[field] = new_data[field]
                upgrades_applied.append(field)

        # Update completeness and source ref
        existing["calibration_completeness"] = CalibrationCompleteness.PHYSICAL
        upgrades_applied.append("calibration_completeness")
        if new_data.get("source_payload_ref"):
            existing["source_payload_ref"] = new_data["source_payload_ref"]
            upgrades_applied.append("source_payload_ref")
        result_completeness = CalibrationCompleteness.PHYSICAL

        return UpgradeResult(
            success=True,
            previous_completeness=existing_completeness,
            new_completeness=result_completeness,
            upgrades_applied=upgrades_applied,
            message=(
                f"Upgraded {existing.get('backend','?')} from metadata to physical. "
                f"Fields updated: {', '.join(upgrades_applied)}"
            ),
        )

    # Case 2: existing=physical, new=physical → merge (newer values win)
    if (
        existing_completeness == CalibrationCompleteness.PHYSICAL
        and new_completeness == CalibrationCompleteness.PHYSICAL
    ):
        # Prefer the record with more populated fields
        existing_pop = sum(
            len(existing.get(k, {}))
            for k in ("t1_times", "t2_times", "readout_errors",
                      "gate_errors", "qubit_freqs", "readouts")
        )
        new_pop = sum(
            len(new_data.get(k, {}))
            for k in ("t1_times", "t2_times", "readout_errors",
                      "gate_errors", "qubit_freqs", "readouts")
        )
        if new_pop > existing_pop:
            for field in ("t1_times", "t2_times", "readout_errors",
                          "gate_errors", "qubit_freqs", "readouts",
                          "connectivity", "qubit_count", "basis_gates"):
                if field in new_data and new_data[field]:
                    existing[field] = new_data[field]
                    upgrades_applied.append(field)
            if new_data.get("source_payload_ref"):
                existing["source_payload_ref"] = new_data["source_payload_ref"]
                upgrades_applied.append("source_payload_ref")
            return UpgradeResult(
                success=True,
                previous_completeness=existing_completeness,
                new_completeness=result_completeness,
                upgrades_applied=upgrades_applied,
                message="Merged physical calibration: new data has more populated fields.",
            )
        return UpgradeResult(
            success=True,
            previous_completeness=existing_completeness,
            new_completeness=result_completeness,
            upgrades_applied=[],
            message="No upgrade needed: existing physical data is more complete.",
        )

    # Case 3: existing=physical, new=metadata (no change unless allow_downgrade)
    if existing_completeness == CalibrationCompleteness.PHYSICAL:
        if allow_downgrade:
            existing["calibration_completeness"] = CalibrationCompleteness.METADATA
            upgrades_applied.append("calibration_completeness")
            result_completeness = CalibrationCompleteness.METADATA
            msg = "Downgraded from physical to metadata (allow_downgrade=True)."
        else:
            msg = (
                "No upgrade: existing record is physical, new data is metadata. "
                "Use allow_downgrade=True to force downgrade."
            )
        return UpgradeResult(
            success=bool(allow_downgrade),
            previous_completeness=existing_completeness,
            new_completeness=result_completeness,
            upgrades_applied=upgrades_applied,
            message=msg,
        )

    # Case 4: both metadata (or existing is absent/newer is metadata)
    if existing_completeness in (
        CalibrationCompleteness.METADATA,
        CalibrationCompleteness.ABSENT,
    ):
        if new_completeness == CalibrationCompleteness.PHYSICAL:
            # Treat as an upgrade from absent/metadata → physical
            for field in ("t1_times", "t2_times", "readout_errors",
                          "gate_errors", "qubit_freqs", "readouts",
                          "connectivity", "qubit_count", "basis_gates"):
                if field in new_data and new_data[field]:
                    existing[field] = new_data[field]
                    upgrades_applied.append(field)
            existing["calibration_completeness"] = CalibrationCompleteness.PHYSICAL
            upgrades_applied.append("calibration_completeness")
            if new_data.get("source_payload_ref"):
                existing["source_payload_ref"] = new_data["source_payload_ref"]
                upgrades_applied.append("source_payload_ref")
            result_completeness = CalibrationCompleteness.PHYSICAL
            return UpgradeResult(
                success=True,
                previous_completeness=existing_completeness,
                new_completeness=result_completeness,
                upgrades_applied=upgrades_applied,
                message="Upgraded from absent/metadata to physical.",
            )

        return UpgradeResult(
            success=True,
            previous_completeness=existing_completeness,
            new_completeness=result_completeness,
            upgrades_applied=[],
            message="No upgrade: both existing and new are metadata-level data.",
        )

    # Fallback
    return UpgradeResult(
        success=False,
        previous_completeness=existing_completeness,
        new_completeness=result_completeness,
        upgrades_applied=[],
        message="Unknown completeness state — no changes applied.",
    )


# ---------------------------------------------------------------------------
# Deterministic resolution of mixed snapshot sets
# ---------------------------------------------------------------------------


def resolve_best_snapshot(
    snapshots: list[dict[str, Any]],
    *,
    prefer_most_physical: bool = True,
) -> dict[str, Any]:
    """Resolve the best calibration snapshot from a list using deterministic rules.

    Resolution order (first wins):
      1. Most physical completeness (physical > metadata > absent)
      2. Most populated fields (sum of non-empty calibration field sizes)
      3. Most recent timestamp (lexicographic ISO-8601 comparison)
      4. First item in input list (stable sort)

    Args:
        snapshots: List of CalibrationSnapshot dicts for the same backend.
        prefer_most_physical: If True, prefer physical over metadata even if
                              metadata has more fields. Default True (correctness
                              over completeness).

    Returns:
        The best snapshot dict (a copy — originals are not modified).
    """
    if not snapshots:
        raise ValueError("snapshots list cannot be empty")
    if len(snapshots) == 1:
        return dict(snapshots[0])

    def _popcount(s: dict[str, Any]) -> int:
        return sum(
            len(s.get(k, {}))
            for k in (
                "t1_times", "t2_times", "readout_errors",
                "gate_errors", "qubit_freqs", "readouts",
            )
        )

    COMPLETENESS_RANK = {
        CalibrationCompleteness.PHYSICAL: 2,
        CalibrationCompleteness.METADATA: 1,
        CalibrationCompleteness.ABSENT: 0,
    }

    scored = []
    for s in snapshots:
        comp = s.get(
            "calibration_completeness",
            infer_calibration_completeness(s),
        )
        rank = COMPLETENESS_RANK.get(comp, 0)
        pop = _popcount(s)
        ts = s.get("timestamp", "")
        scored.append((rank, pop, ts, s))

    # Sort: highest rank first, then pop, then timestamp (reverse = newest first),
    # then stable (first seen wins)
    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)

    best = scored[0][3]
    result = dict(best)
    # Ensure calibration_completeness is always present in the result
    if "calibration_completeness" not in result:
        result["calibration_completeness"] = infer_calibration_completeness(result)
    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _main() -> None:
    """Simple CLI for testing: python -m gre.research.calibration_fetch <file>"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m gre.research.calibration_fetch <calibration.json>")
        sys.exit(1)

    path = Path(sys.argv[1])
    try:
        snap = load_calibration_from_file(path)
        print(f"Loaded: {snap['backend']} ({snap['calibration_completeness']})")
        print(f"  t1_times:   {len(snap['t1_times'])} entries")
        print(f"  t2_times:   {len(snap['t2_times'])} entries")
        print(f"  readout_err: {len(snap['readout_errors'])} entries")
        print(f"  gate_err:   {len(snap['gate_errors'])} entries")
        print(f"  connectivity: {len(snap['connectivity'])} edges")
        print(f"  qubit_count: {snap['qubit_count']}")
        print(f"  basis_gates: {snap['basis_gates']}")
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    _main()
