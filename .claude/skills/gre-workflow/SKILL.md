---
description: Run a structured GRE workflow using a forked subagent for research, audit, or implementation tasks across corpus, quantum, and calibration modules.
argument-hint: [task]
context: fork
disable-model-invocation: true
allowed-tools: Read Grep Glob Edit Write MultiEdit Bash(python *) Bash(git status *)
---

# GRE workflow

Task: $ARGUMENTS

Instructions:
1. Clarify the target in one sentence.
2. Inspect relevant files only.
3. Produce findings, risks, exact file edits needed, and tests needed.
4. If changes are requested, apply minimal edits and run verification.
5. Return concise scientific output with no filler.
