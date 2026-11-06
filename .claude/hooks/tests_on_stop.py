"""Stop hook (informative): run the test suite when Python files changed since the last run.

Runs when Claude finishes a turn. If any .py file under powersim/ or tests/ changed since the
previous run, it runs pytest; on failure it shows a warning to the user. It never blocks Claude
from finishing (see the discussion in .claude/CLAUDE.md).
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
STATE_FILE = Path(__file__).with_name(".tests_on_stop_state")
WATCHED = ("powersim", "tests")
MAX_FAILURE_LINES = 15


def fingerprint() -> str:
    digest = hashlib.sha256()
    for folder in WATCHED:
        for path in sorted((PROJECT / folder).rglob("*.py")):
            stat = path.stat()
            digest.update(
                f"{path.relative_to(PROJECT)}|{stat.st_size}|{stat.st_mtime_ns}\n".encode()
            )
    return digest.hexdigest()


def main() -> None:
    sys.stdin.read()  # hook payload, not needed

    current = fingerprint()
    if STATE_FILE.exists() and STATE_FILE.read_text(encoding="utf-8") == current:
        return
    STATE_FILE.write_text(current, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=no", "-rf"],
        cwd=PROJECT,
        capture_output=True,
        text=True,
        timeout=170,
    )
    if result.returncode in (0, 5):  # 5: no tests collected
        return

    lines = [line for line in result.stdout.splitlines() if line.startswith(("FAILED", "ERROR"))]
    summary = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "pytest failed"
    details = "\n".join(lines[:MAX_FAILURE_LINES])
    print(json.dumps({"systemMessage": f"Tests failing after this turn: {summary}\n{details}"}))


if __name__ == "__main__":
    main()
