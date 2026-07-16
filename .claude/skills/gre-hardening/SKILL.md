---
description: Run GRE corpus hardening tasks including taxonomy backfill, provenance checks, validation tiers, calibration completeness, and corpus report diagnostics.
disable-model-invocation: true
allowed-tools: Read Grep Glob Edit Write MultiEdit Bash(python *) Bash(git diff *) Bash(git status *)
paths:
  - "gre/research/**"
  - "docs/**"
  - "imports/**"
  - "tests/**"
---

# GRE hardening

Instructions:
1. Check schema compliance.
2. Check provenance coverage.
3. Check evidence class and validation tier consistency.
4. Check backend generation normalization.
5. Check calibration completeness semantics.
6. Update corpus report if any artifact changes.
7. Add or update tests for every hardening rule change.
8. Prefer minimal diffs and deterministic behavior.
