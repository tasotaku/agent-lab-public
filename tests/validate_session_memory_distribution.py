#!/usr/bin/env python3
"""Frozen distribution contract for the opt-in public session-memory feature."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "SESSION_MEMORY_CONTRACT.md",
    "tools/session_memory.py",
    "tests/test_session_memory.py",
}
README_MARKERS = (
    "install-memory",
    "check-memory",
    "memory-record",
    "memory-context",
    "remove-memory",
)


def main() -> int:
    failures: list[str] = []
    missing = sorted(path for path in REQUIRED if not (ROOT / path).is_file())
    if missing:
        failures.append("missing required paths: " + ", ".join(missing))

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    absent = [marker for marker in README_MARKERS if marker not in readme]
    if absent:
        failures.append("README missing commands: " + ", ".join(absent))

    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    if "session memory lifecycle" not in workflow.lower():
        failures.append("CI does not expose the session memory lifecycle check")

    if not missing:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "tests.test_session_memory"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode:
            failures.append("session-memory tests failed:\n" + result.stdout + result.stderr)

    if failures:
        print("FAIL: public session-memory distribution")
        for failure in failures:
            print("- " + failure)
        return 1
    print("PASS: public session-memory distribution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
