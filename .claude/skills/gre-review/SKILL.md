---
description: Perform a rigorous scientific code review for GRE focused on correctness, provenance, taxonomy integrity, calibration semantics, regression risk, and test adequacy.
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash(git diff *) Bash(git status *) Bash(python -m pytest *)
paths:
  - "gre/**"
  - "tests/**"
  - "docs/**"
---

# GRE review

Instructions:
1. Review only from current repository evidence.
2. Prioritize schema integrity, provenance correctness, calibration semantics, evidence-class separation, deterministic normalization, and test coverage gaps.
3. Output critical issues, medium issues, low issues, and suggested tests.
4. Avoid style-only feedback unless it affects correctness or maintainability.
