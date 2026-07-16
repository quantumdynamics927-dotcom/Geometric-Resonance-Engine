from pathlib import Path
import json

root = Path.cwd()
messages = []

for p in [
    root / "README.md",
    root / "docs" / "research_corpus.md",
    root / "docs" / "corpus_taxonomy.md",
]:
    if p.exists():
        messages.append(f"Context file available: {p.as_posix()}")

messages.append("Project mode: scientific terminology only; avoid mystical framing.")
messages.append("Priority: preserve provenance, schema integrity, and calibration semantics.")
messages.append("Do not treat synthetic_seed as historical_real.")
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": "\n".join(messages)
    }
}))