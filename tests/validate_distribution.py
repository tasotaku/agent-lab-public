#!/usr/bin/env python3
"""Deterministic release contract for agent-lab-public."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    ".github/workflows/ci.yml",
    ".gitignore",
    "LICENSE",
    "README.md",
    "SESSION_MEMORY_CONTRACT.md",
    "bootstrap.py",
    "rules/core.md",
    "skills/shared/test/SKILL.md",
    "skills/codex/make-portable/SKILL.md",
    "tools/audit_public.py",
    "tools/session_memory.py",
    "tests/test_bootstrap.py",
    "tests/test_session_memory.py",
    "tests/validate_session_memory_distribution.py",
    "tests/test_audit_public.py",
}
FORBIDDEN_ROOTS = {
    ".agent-lab",
    ".claude",
    ".codex",
    ".loop-engineering",
    "knowledge",
    "research",
    "user-config",
}


def run(*command: str) -> subprocess.CompletedProcess[str]:
    # Validators execute only public, repository-owned entry points and
    # retain their output so a failing contract remains directly diagnosable.
    return subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def main() -> int:
    # Structural failures are reported before executable checks so an
    # empty or privacy-stripped shell cannot pass by merely exiting successfully.
    failures: list[str] = []
    missing = sorted(path for path in REQUIRED if not (ROOT / path).exists())
    if missing:
        failures.append("missing required paths: " + ", ".join(missing))
    present_forbidden = sorted(path for path in FORBIDDEN_ROOTS if (ROOT / path).exists())
    if present_forbidden:
        failures.append("forbidden roots present: " + ", ".join(present_forbidden))

    readme_path = ROOT / "README.md"
    if readme_path.exists():
        readme = readme_path.read_text(encoding="utf-8")
        expected_text = [
            "git clone https://github.com/tasotaku/agent-lab-public.git",
            "python bootstrap.py install",
            "python bootstrap.py check",
            "python bootstrap.py smoke",
            "python tools/audit_public.py",
            "Windows",
            "macOS",
            "Linux",
        ]
        absent = [text for text in expected_text if text not in readme]
        if absent:
            failures.append("README missing public entry text: " + ", ".join(absent))

    if not missing:
        tests = run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py")
        if tests.returncode:
            failures.append("unit tests failed:\n" + tests.stdout + tests.stderr)

        audit = run(sys.executable, "tools/audit_public.py", "--format", "json")
        if audit.returncode:
            failures.append("public audit failed:\n" + audit.stdout + audit.stderr)
        else:
            try:
                report = json.loads(audit.stdout)
            except json.JSONDecodeError as error:
                failures.append(f"public audit did not return JSON: {error}")
            else:
                for category in ["credentials", "personal_config", "private_knowledge", "conversations", "private_dependencies"]:
                    if report.get("categories", {}).get(category) != "PASS":
                        failures.append(f"public audit category did not pass: {category}")
                if report.get("scanned", {}).get("files", 0) < 20:
                    failures.append("public payload is too small to establish a substantive distribution")

    if failures:
        print("FAIL: public distribution contract")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("PASS: public distribution contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
