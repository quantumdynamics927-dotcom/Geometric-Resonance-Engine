import json
import sys

payload = json.load(sys.stdin)
cmd = payload.get("tool_input", {}).get("command", "")

blocked = [
    "rm -rf /",
    "git push --force",
    "git reset --hard",
    "del /s /q",
]

for token in blocked:
    if token in cmd:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"Blocked unsafe command: {token}"
            }
        }))
        raise SystemExit(2)

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow"
    }
}))
