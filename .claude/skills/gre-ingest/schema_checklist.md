# Ingestion checklist

Required provenance fields:
- artifact_id
- source_project
- source_path
- source_date
- import_date
- artifact_type
- transform_chain
- sensitivity

Required semantic fields where applicable:
- backend
- depth
- shots
- metrics
- validation_tier
- evidence_class
- backend_generation

Rules:
- calibration snapshots can be metadata-only or physical
- synthetic_seed must never be promoted to historical_real
- markdown files are sidecars, not primary artifacts
