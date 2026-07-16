---
description: Work on graph-to-circuit mapping, quantum walk circuit builders, qutrit encoding, Qiskit compatibility, and graceful degradation when Qiskit is unavailable.
disable-model-invocation: true
allowed-tools: Read Grep Glob Edit Write MultiEdit Bash(python *)
paths:
  - "gre/quantum/**"
  - "gre/core/**"
  - "tests/**"
---

# GRE circuit

Instructions:
1. Preserve no-Qiskit graceful degradation.
2. Keep metadata complete on CircuitModel outputs.
3. Prefer deterministic circuit generation.
4. When adding encoding or walk logic, add tests for both available and unavailable Qiskit environments.
5. Do not break existing corpus integration paths.
