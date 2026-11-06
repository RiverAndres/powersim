"""PreToolUse hook: deny any tool call that references the secrets in env/ or .env.

Permission rules (Read deny) only cover the file tools; this also covers shell commands
such as `cat env/...` or `Get-Content env\\...`. It is a safety net against accidents,
not a sandbox.
"""

import json
import re
import sys

# env/ or env\ as a path segment, or a .env file. Does not match .venv, $env:Path,
# VIRTUAL_ENV, getenv, .envrc, ...
SECRET_PATH = re.compile(
    r"(?:^|[\s\"'=(/\\:;,&|<>`])(?:env[/\\]|\.env\b(?![.\w-]*rc))", re.IGNORECASE
)


def main() -> None:
    payload = json.load(sys.stdin)
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    if tool_name in ("Bash", "PowerShell"):
        fields = [tool_input.get("command", "")]
    else:
        # File tools: check only the paths they touch, not the content being written
        # (otherwise editing any text that mentions the secrets folder would be blocked).
        keys = ("file_path", "path", "pattern") if tool_name == "Glob" else ("file_path", "path")
        fields = [tool_input.get(key, "") for key in keys]
    text = " ".join(str(field) for field in fields)

    if SECRET_PATH.search(text):
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            "Blocked by .claude/hooks/guard_secrets.py: env/ and .env hold the "
                            "user's secrets (ESIOS token) and must never be read or shown."
                        ),
                    }
                }
            )
        )


if __name__ == "__main__":
    main()
