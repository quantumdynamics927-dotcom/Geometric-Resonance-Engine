---
description: Upgrade backend calibration artifacts from metadata-level to physical where source payloads exist, and propagate calibration completeness through GRE quality gates.
disable-model-invocation: true
allowed-tools: Read Grep Glob Edit Write MultiEdit Bash(python *)
paths:
  - "gre/research/**"
  - "imports/calibration/**"
  - "docs/**"
  - "tests/**"
---

# GRE calibration

Instructions:
1. Locate calibration payloads or saved exports for target backends.
2. Parse physical fields where available.
3. Update canonical calibration snapshot without breaking metadata-only compatibility.
4. Recompute calibration completeness.
5. Recompute quality gates and evidence chain summaries impacted by calibration semantics.
6. Add tests for upgrade and fallback behavior.

Load calibration_fields.md when needed.
