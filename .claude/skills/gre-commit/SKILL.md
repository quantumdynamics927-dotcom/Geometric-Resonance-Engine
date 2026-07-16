---
description: Stage and commit GRE changes with a disciplined scientific commit message after reviewing diff, tests, and regression risks.
disable-model-invocation: true
allowed-tools: Bash(git status *) Bash(git diff *) Bash(git add *) Bash(git commit *) Read
---

# GRE commit

## Context
- Git status:
!git status --short
- Git diff:
!git diff --stat && git diff HEAD

## Instructions
1. Summarize the change set.
2. Flag any regression or missing-test risk.
3. If acceptable, stage relevant files.
4. Create a precise commit message in imperative mood.
5. Do not push.
