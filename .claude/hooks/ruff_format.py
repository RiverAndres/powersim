"""PostToolUse hook: run `ruff format` on the Python file that was just written or edited."""

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input", {})
    tool_response = payload.get("tool_response") or {}
    file_path = tool_input.get("file_path") or tool_response.get("filePath")

    if not file_path or Path(file_path).suffix != ".py" or not Path(file_path).is_file():
        return

    # sys.executable is the venv python that runs this hook, which has ruff installed.
    subprocess.run([sys.executable, "-m", "ruff", "format", "--quiet", file_path], check=False)


if __name__ == "__main__":
    main()
