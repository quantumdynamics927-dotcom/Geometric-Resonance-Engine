# Calibration fields

Physical calibration target fields:
- retrieval_timestamp
- qubit_count
- T1_summary
- T2_summary
- readout_error_summary
- gate_error_summary
- basis_gates
- source_payload_reference

Rules:
- metadata-only remains valid
- physical requires actual physical fields, not inferred placeholders
- preserve provenance of payload source
