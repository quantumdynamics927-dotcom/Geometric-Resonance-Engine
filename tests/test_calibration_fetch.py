"""Tests for gre/research/calibration_fetch.py."""

import pytest
from gre.research import calibration_fetch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


METADATA_SNAPSHOT = {
    "backend": "ibm_kingston",
    "timestamp": "2026-04-23T12:00:00Z",
    "t1_times": {},
    "t2_times": {},
    "readout_errors": {},
    "gate_errors": {},
    "qubit_freqs": {},
    "readouts": {},
    "connectivity": [],
    "calibration_completeness": "metadata",
    "qubit_count": None,
    "basis_gates": [],
    "source_payload_ref": None,
}


PHYSICAL_PAYLOAD = {
    "backend": "ibm_kingston",
    "timestamp": "2026-04-23T12:00:00Z",
    "t1_times": {"0": 95.3, "1": 102.1, "2": 88.7},
    "t2_times": {"0": 180.2, "1": 175.6, "2": 190.1},
    "readout_errors": {"0": 0.021, "1": 0.018},
    "gate_errors": {"cx0_1": 0.0061, "sx0": 0.0012},
    "qubit_freqs": {"0": 4.9876, "1": 5.0123},
    "readouts": {"0": 0.979, "1": 0.982},
    "connectivity": [[0, 1], [1, 2]],
    "qubit_count": 127,
    "basis_gates": ["cx", "sx", "x", "rz", "id"],
    "source": "ibm-quantum-api",
}


METADATA_ONLY_PAYLOAD = {
    "backend": "ibm_fez",
    "timestamp": "2026-03-05T09:00:00Z",
    "calibration_completeness": "metadata",
    # No t1_times / t2_times — purely a metadata record
}


# ---------------------------------------------------------------------------
# infer_calibration_completeness
# ---------------------------------------------------------------------------


class TestInferCalibrationCompleteness:
    def test_physical_when_t1_and_t2_present(self):
        assert (
            calibration_fetch.infer_calibration_completeness(PHYSICAL_PAYLOAD)
            == "physical"
        )

    def test_metadata_when_t1_empty_t2_present(self):
        payload = dict(PHYSICAL_PAYLOAD)
        payload["t1_times"] = {}  # empty — not physical
        assert calibration_fetch.infer_calibration_completeness(payload) == "metadata"

    def test_metadata_when_t2_empty_t1_present(self):
        payload = dict(PHYSICAL_PAYLOAD)
        payload["t2_times"] = {}  # empty — not physical
        assert calibration_fetch.infer_calibration_completeness(payload) == "metadata"

    def test_metadata_when_only_backend_present(self):
        assert (
            calibration_fetch.infer_calibration_completeness({"backend": "ibm_kingston"})
            == "metadata"
        )

    def test_metadata_when_only_connectivity_present(self):
        assert (
            calibration_fetch.infer_calibration_completeness(
                {"connectivity": [[0, 1], [1, 2]]}
            )
            == "metadata"
        )

    def test_absent_when_no_calibration_fields(self):
        assert (
            calibration_fetch.infer_calibration_completeness(
                {"something_else": "value"}
            )
            == "absent"
        )

    def test_absent_with_empty_dict(self):
        assert calibration_fetch.infer_calibration_completeness({}) == "absent"


# ---------------------------------------------------------------------------
# has_physical_calibration_data
# ---------------------------------------------------------------------------


class TestHasPhysicalCalibrationData:
    def test_true_when_t1_and_t2_non_empty(self):
        assert calibration_fetch.has_physical_calibration_data(PHYSICAL_PAYLOAD) is True

    def test_false_when_t1_empty(self):
        payload = dict(PHYSICAL_PAYLOAD)
        payload["t1_times"] = {}
        assert calibration_fetch.has_physical_calibration_data(payload) is False

    def test_false_when_t2_empty(self):
        payload = dict(PHYSICAL_PAYLOAD)
        payload["t2_times"] = {}
        assert calibration_fetch.has_physical_calibration_data(payload) is False

    def test_false_when_t1_not_dict(self):
        payload = dict(PHYSICAL_PAYLOAD)
        payload["t1_times"] = "not_a_dict"
        assert calibration_fetch.has_physical_calibration_data(payload) is False

    def test_false_when_t2_not_dict(self):
        payload = dict(PHYSICAL_PAYLOAD)
        payload["t2_times"] = "not_a_dict"
        assert calibration_fetch.has_physical_calibration_data(payload) is False


# ---------------------------------------------------------------------------
# parse_ibm_calibration_payload
# ---------------------------------------------------------------------------


class TestParseIbmCalibrationPayload:
    def test_parses_physical_payload(self):
        result = calibration_fetch.parse_ibm_calibration_payload(
            PHYSICAL_PAYLOAD, source_ref="/path/to/ibm_api_response.json"
        )
        assert result["backend"] == "ibm_kingston"
        assert result["timestamp"] == "2026-04-23T12:00:00Z"
        assert result["t1_times"] == {"0": 95.3, "1": 102.1, "2": 88.7}
        assert result["t2_times"] == {"0": 180.2, "1": 175.6, "2": 190.1}
        assert result["readout_errors"] == {"0": 0.021, "1": 0.018}
        assert result["gate_errors"] == {"cx0_1": 0.0061, "sx0": 0.0012}
        assert result["qubit_freqs"] == {"0": 4.9876, "1": 5.0123}
        assert result["readouts"] == {"0": 0.979, "1": 0.982}
        assert result["connectivity"] == [[0, 1], [1, 2]]
        assert result["qubit_count"] == 127
        assert result["basis_gates"] == ["cx", "sx", "x", "rz", "id"]
        assert result["calibration_completeness"] == "physical"
        assert result["source_payload_ref"] == "/path/to/ibm_api_response.json"

    def test_parses_string_qubit_count(self):
        payload = dict(PHYSICAL_PAYLOAD)
        payload["qubit_count"] = "127"  # IBM sometimes returns string
        result = calibration_fetch.parse_ibm_calibration_payload(payload)
        assert result["qubit_count"] == 127

    def test_missing_backend_raises(self):
        payload = {"timestamp": "2026-04-23T12:00:00Z", "t1_times": {"0": 1.0}}
        with pytest.raises(ValueError, match="backend"):
            calibration_fetch.parse_ibm_calibration_payload(payload)

    def test_missing_timestamp_raises(self):
        payload = {"backend": "ibm_kingston", "t1_times": {"0": 1.0}}
        with pytest.raises(ValueError, match="timestamp"):
            calibration_fetch.parse_ibm_calibration_payload(payload)

    def test_camelcase_backend_name_normalised(self):
        payload = dict(PHYSICAL_PAYLOAD)
        del payload["backend"]
        payload["backend_name"] = "ibm_kingston"  # camelCase variant
        result = calibration_fetch.parse_ibm_calibration_payload(payload)
        assert result["backend"] == "ibm_kingston"

    def test_camelcase_timestamp_normalised(self):
        payload = dict(PHYSICAL_PAYLOAD)
        del payload["timestamp"]
        payload["created"] = "2026-04-23T12:00:00Z"  # alternate field
        result = calibration_fetch.parse_ibm_calibration_payload(payload)
        assert result["timestamp"] == "2026-04-23T12:00:00Z"

    def test_catches_missing_t1_and_t2(self):
        # Missing T1/T2 is detected by infer_completeness not parse
        payload = {
            "backend": "ibm_kingston",
            "timestamp": "2026-04-23T12:00:00Z",
            # no t1_times or t2_times
        }
        result = calibration_fetch.parse_ibm_calibration_payload(payload)
        assert result["calibration_completeness"] == "metadata"


# ---------------------------------------------------------------------------
# upgrade_calibration_snapshot
# ---------------------------------------------------------------------------


class TestUpgradeCalibrationSnapshot:
    def test_metadata_to_physical_upgrade(self):
        existing = dict(METADATA_SNAPSHOT)
        new_data = calibration_fetch.parse_ibm_calibration_payload(
            PHYSICAL_PAYLOAD, source_ref="/path/to/physical.json"
        )
        result = calibration_fetch.upgrade_calibration_snapshot(existing, new_data)
        assert result.success is True
        assert result.previous_completeness == "metadata"
        assert result.new_completeness == "physical"
        assert "t1_times" in result.upgrades_applied
        assert "t2_times" in result.upgrades_applied
        assert "calibration_completeness" in result.upgrades_applied
        # Existing is modified in place
        assert existing["calibration_completeness"] == "physical"
        assert existing["t1_times"] == {"0": 95.3, "1": 102.1, "2": 88.7}

    def test_physical_to_physical_merge(self):
        existing = {
            **calibration_fetch.parse_ibm_calibration_payload(PHYSICAL_PAYLOAD),
            "calibration_completeness": "physical",
        }
        # Newer payload with more qubits
        newer = {
            "backend": "ibm_kingston",
            "timestamp": "2026-04-24T12:00:00Z",
            "t1_times": {"0": 95.3, "1": 102.1, "2": 88.7, "3": 91.0},
            "t2_times": {"0": 180.2, "1": 175.6, "2": 190.1, "3": 185.0},
            "readout_errors": {"0": 0.021, "1": 0.018, "2": 0.019, "3": 0.020},
            "gate_errors": {},
            "qubit_freqs": {},
            "readouts": {},
            "connectivity": [],
            "qubit_count": 127,
            "basis_gates": [],
        }
        result = calibration_fetch.upgrade_calibration_snapshot(existing, newer)
        assert result.success is True
        assert result.previous_completeness == "physical"
        assert result.new_completeness == "physical"

    def test_physical_to_physical_keeps_existing_when_more_complete(self):
        existing = {
            **calibration_fetch.parse_ibm_calibration_payload(PHYSICAL_PAYLOAD),
            "calibration_completeness": "physical",
        }
        # Newer but with fewer populated fields
        newer = {
            "backend": "ibm_kingston",
            "timestamp": "2026-04-24T12:00:00Z",
            "t1_times": {"0": 95.3},  # fewer entries
            "t2_times": {"0": 180.2},
            "readout_errors": {},
            "gate_errors": {},
            "qubit_freqs": {},
            "readouts": {},
            "connectivity": [],
            "qubit_count": 127,
            "basis_gates": [],
        }
        result = calibration_fetch.upgrade_calibration_snapshot(existing, newer)
        assert result.success is True
        assert result.upgrades_applied == []
        assert "existing physical data is more complete" in result.message

    def test_physical_existing_metadata_new_preserved_without_downgrade(self):
        existing = {
            **calibration_fetch.parse_ibm_calibration_payload(PHYSICAL_PAYLOAD),
            "calibration_completeness": "physical",
        }
        newer = dict(METADATA_ONLY_PAYLOAD)
        result = calibration_fetch.upgrade_calibration_snapshot(existing, newer)
        assert result.success is False
        assert result.previous_completeness == "physical"
        assert result.new_completeness == "physical"
        assert existing["calibration_completeness"] == "physical"

    def test_physical_existing_metadata_new_downgrades_when_allowed(self):
        existing = {
            **calibration_fetch.parse_ibm_calibration_payload(PHYSICAL_PAYLOAD),
            "calibration_completeness": "physical",
        }
        newer = dict(METADATA_ONLY_PAYLOAD)
        result = calibration_fetch.upgrade_calibration_snapshot(
            existing, newer, allow_downgrade=True
        )
        assert result.success is True
        assert result.previous_completeness == "physical"
        assert result.new_completeness == "metadata"

    def test_metadata_existing_metadata_new_no_change(self):
        existing = dict(METADATA_SNAPSHOT)
        newer = dict(METADATA_ONLY_PAYLOAD)
        result = calibration_fetch.upgrade_calibration_snapshot(existing, newer)
        assert result.success is True
        assert result.upgrades_applied == []
        assert "both existing and new are metadata-level" in result.message

    def test_absent_to_physical_upgrade(self):
        existing = {
            "backend": "ibm_kingston",
            "timestamp": "2026-04-23T12:00:00Z",
            "calibration_completeness": "absent",
        }
        newer = calibration_fetch.parse_ibm_calibration_payload(
            PHYSICAL_PAYLOAD, source_ref="/path/to/physical.json"
        )
        result = calibration_fetch.upgrade_calibration_snapshot(existing, newer)
        assert result.success is True
        assert result.previous_completeness == "absent"
        assert result.new_completeness == "physical"

    def test_missing_t1_in_new_data_raises(self):
        existing = dict(METADATA_SNAPSHOT)
        newer = {
            "backend": "ibm_kingston",
            "timestamp": "2026-04-23T12:00:00Z",
            "t2_times": {"0": 180.2},
            # No t1_times → not physical, hits Case 4 (metadata→metadata, no change).
            # To hit Case 1 (metadata→physical) we need both t1 and t2 absent.
            # So this test is invalid for the "raise on missing T1" invariant.
            # We test the invariant differently: a payload that claims physical
            # but is missing T1 should raise.
            "calibration_completeness": "physical",  # explicit — pretends to be physical
            "readout_errors": {"0": 0.02},  # makes it look physical to infer_completeness
            "gate_errors": {},
            "qubit_freqs": {},
            "readouts": {},
            "connectivity": [],
            "basis_gates": [],
        }
        # Newer claims to be physical but has no t1_times → should raise
        with pytest.raises(ValueError, match="t1_times"):
            calibration_fetch.upgrade_calibration_snapshot(existing, newer)

    def test_missing_t2_in_new_data_raises(self):
        existing = dict(METADATA_SNAPSHOT)
        newer = {
            "backend": "ibm_kingston",
            "timestamp": "2026-04-23T12:00:00Z",
            "t1_times": {"0": 95.3},
            "calibration_completeness": "physical",
            "readout_errors": {"0": 0.02},
            "gate_errors": {},
            "qubit_freqs": {},
            "readouts": {},
            "connectivity": [],
            "basis_gates": [],
        }
        with pytest.raises(ValueError, match="t2_times"):
            calibration_fetch.upgrade_calibration_snapshot(existing, newer)

    def test_empty_t1_in_new_data_raises(self):
        existing = dict(METADATA_SNAPSHOT)
        newer = {
            "backend": "ibm_kingston",
            "timestamp": "2026-04-23T12:00:00Z",
            "t1_times": {},
            "t2_times": {"0": 180.2},
            "calibration_completeness": "physical",
            "readout_errors": {"0": 0.02},
            "gate_errors": {},
            "qubit_freqs": {},
            "readouts": {},
            "connectivity": [],
            "basis_gates": [],
        }
        with pytest.raises(ValueError, match="t1_times"):
            calibration_fetch.upgrade_calibration_snapshot(existing, newer)

    def test_upgrade_result_to_dict(self):
        result = calibration_fetch.UpgradeResult(
            success=True,
            previous_completeness="metadata",
            new_completeness="physical",
            upgrades_applied=["t1_times", "t2_times"],
            message="Test upgrade",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["previous_completeness"] == "metadata"
        assert d["new_completeness"] == "physical"
        assert "t1_times" in d["upgrades_applied"]

    def test_upgrade_result_repr(self):
        result = calibration_fetch.UpgradeResult(
            success=True,
            previous_completeness="metadata",
            new_completeness="physical",
            upgrades_applied=["t1_times"],
            message="Test upgrade",
        )
        r = repr(result)
        assert "success=True" in r
        assert "metadata→physical" in r


# ---------------------------------------------------------------------------
# resolve_best_snapshot
# ---------------------------------------------------------------------------


class TestResolveBestSnapshot:
    def test_single_snapshot_returned(self):
        snap = dict(METADATA_SNAPSHOT)
        result = calibration_fetch.resolve_best_snapshot([snap])
        assert result == snap
        assert result is not snap  # should be a copy

    def test_empty_list_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            calibration_fetch.resolve_best_snapshot([])

    def test_physical_preferred_over_metadata(self):
        metadata = dict(METADATA_SNAPSHOT)
        physical = calibration_fetch.parse_ibm_calibration_payload(PHYSICAL_PAYLOAD)
        # Order reversed so physical would be first only if sorting works
        result = calibration_fetch.resolve_best_snapshot([metadata, physical])
        assert result["calibration_completeness"] == "physical"

    def test_metadata_preferred_over_absent(self):
        metadata = dict(METADATA_SNAPSHOT)
        absent = {"backend": "ibm_kingston", "timestamp": "2026-04-23T12:00:00Z"}
        result = calibration_fetch.resolve_best_snapshot([absent, metadata])
        assert result["calibration_completeness"] == "metadata"

    def test_most_populated_wins_at_same_tier(self):
        less_physical = calibration_fetch.parse_ibm_calibration_payload(PHYSICAL_PAYLOAD)
        more_physical = calibration_fetch.parse_ibm_calibration_payload(PHYSICAL_PAYLOAD)
        # Add extra fields to more_physical
        more_physical["t1_times"]["3"] = 91.0
        more_physical["t2_times"]["3"] = 185.0
        more_physical["readout_errors"]["3"] = 0.022
        result = calibration_fetch.resolve_best_snapshot([less_physical, more_physical])
        assert result == more_physical

    def test_newest_timestamp_wins_at_same_tier_same_population(self):
        older = calibration_fetch.parse_ibm_calibration_payload(PHYSICAL_PAYLOAD)
        older["timestamp"] = "2026-04-23T00:00:00Z"
        newer = calibration_fetch.parse_ibm_calibration_payload(PHYSICAL_PAYLOAD)
        newer["timestamp"] = "2026-04-24T00:00:00Z"
        result = calibration_fetch.resolve_best_snapshot([older, newer])
        assert result["timestamp"] == "2026-04-24T00:00:00Z"

    def test_does_not_modify_originals(self):
        originals = [dict(METADATA_SNAPSHOT), dict(METADATA_SNAPSHOT)]
        calibration_fetch.resolve_best_snapshot(originals)
        # originals should be unchanged
        assert originals[0]["calibration_completeness"] == "metadata"
        assert originals[1]["calibration_completeness"] == "metadata"
