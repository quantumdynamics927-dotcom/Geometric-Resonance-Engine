from pathlib import Path
import subprocess
import json

root = Path.cwd()
commands = []

if (root / "pyproject.toml").exists() or (root / "pytest.ini").exists():
    commands.append(["python", "-m", "pytest", "-q", "--tb=short"])

results = []
for cmd in commands:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=str(root))
        results.append({
            "command": " ".join(cmd),
            "returncode": proc.returncode,
            "stdout": proc.stdout[-3000:],
            "stderr": proc.stderr[-3000:]
        })
    except Exception as e:
        results.append({
            "command": " ".join(cmd),
            "error": str(e)
        })

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": json.dumps(results)
    }
}))
