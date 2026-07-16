---
description: Import QSG, IBM Quantum, Sierpinski, calibration, TMT, or related historical research artifacts into GRE corpus schemas with provenance sidecars and summaries.
argument-hint: [source-path-or-project]
disable-model-invocation: true
allowed-tools: Read Grep Glob Edit Write MultiEdit Bash(python *) Bash(git status *) Bash(dir *) Bash(ls *)
paths:
  - "gre/research/**"
  - "imports/**"
  - "docs/**"
---

# GRE ingestion

Target: $ARGUMENTS

Instructions:
1. Identify whether the source is hardware runs, Sierpinski experiments, calibration snapshots, or derived summaries.
2. Normalize into canonical GRE schemas.
3. Generate or update primary JSON, provenance JSON, and summary markdown.
4. Preserve source filename where practical.
5. Mark evidence class correctly.
6. Do not invent metrics absent from source data.
7. Run schema validation and corpus report updates.

Before editing, read schema_checklist.md.
