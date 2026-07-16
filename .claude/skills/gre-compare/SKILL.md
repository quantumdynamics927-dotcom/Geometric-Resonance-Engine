---
description: Compare generated geometry, graph, walk, or circuit outputs against the imported GRE corpus and report evidence chains, similarity, and claim support.
argument-hint: [generated-object-or-path]
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash(python *)
paths:
  - "gre/**"
  - "examples/**"
  - "imports/**"
---

# GRE compare

Object or path: $ARGUMENTS

Instructions:
1. Load corpus if needed.
2. Resolve the generated descriptor or file.
3. Compare against relevant historical artifacts.
4. Report top matching artifacts, similarity metrics, evidence chain, calibration completeness, and whether support is historical_real or synthetic_seed.
5. Do not overstate claims when only metadata-level calibration exists.

Load metrics.md if needed.
