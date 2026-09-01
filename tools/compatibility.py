#!/usr/bin/env python3
"""Show exact-commit cross-platform CI evidence without GitHub sign-in."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com/repos/tasotaku/agent-lab-public"
REQUIRED_OS = {"windows-latest", "macos-latest", "ubuntu-latest"}
REQUIRED_STEPS = {
    "Install into isolated home",
    "Check isolated installation",
    "Load installed capability",
    "Audit public payload and history",
    "Run unit and distribution tests",
}


def get_json(url: str) -> dict[str, Any]:
    # The request intentionally has no Authorization header, proving that the
    # evidence is available to an unsigned public-repository visitor.
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "agent-lab-public-compatibility"})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def current_commit() -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "cannot read current commit")
    return result.stdout.strip()


def evaluate(commit: str, runs: dict[str, Any], jobs: dict[str, Any]) -> tuple[list[dict[str, str]], list[str]]:
    # Job and step conclusions are public structured evidence even when GitHub's
    # raw log viewer asks an unsigned browser to sign in.
    failures: list[str] = []
    matching_runs = [
        run for run in runs.get("workflow_runs", [])
        if run.get("head_sha") == commit and run.get("name") == "Cross-platform install" and run.get("conclusion") == "success"
    ]
    if not matching_runs:
        failures.append(f"no successful Cross-platform install run for {commit}")
    evidence: list[dict[str, str]] = []
    seen_os: set[str] = set()
    for job in jobs.get("jobs", []):
        name = str(job.get("name", ""))
        os_name = next((candidate for candidate in REQUIRED_OS if candidate in name), "")
        if not os_name:
            continue
        seen_os.add(os_name)
        step_results = {str(step.get("name")): str(step.get("conclusion")) for step in job.get("steps", [])}
        missing = sorted(step for step in REQUIRED_STEPS if step_results.get(step) != "success")
        if job.get("conclusion") != "success" or missing:
            failures.append(f"{name} missing successful steps: {', '.join(missing)}")
        evidence.append(
            {
                "job": name,
                "os": os_name,
                "conclusion": str(job.get("conclusion")),
                "components": "PASS" if not missing else "FAIL",
                "url": str(job.get("html_url", "")),
            }
        )
    missing_os = sorted(REQUIRED_OS - seen_os)
    if missing_os:
        failures.append("missing OS jobs: " + ", ".join(missing_os))
    return evidence, failures


def main() -> int:
    try:
        commit = current_commit()
        runs = get_json(f"{API}/actions/runs?head_sha={commit}&event=push&per_page=20")
        matching = next(
            (
                run for run in runs.get("workflow_runs", [])
                if run.get("head_sha") == commit and run.get("name") == "Cross-platform install" and run.get("conclusion") == "success"
            ),
            None,
        )
        jobs = get_json(str(matching["jobs_url"])) if matching else {"jobs": []}
        evidence, failures = evaluate(commit, runs, jobs)
    except (HTTPError, URLError, OSError, RuntimeError, KeyError) as error:
        print(f"FAIL: could not obtain unsigned compatibility evidence: {error}", file=sys.stderr)
        return 2
    print(f"COMMIT: {commit}")
    print("AUTHENTICATION: none")
    print("WORKFLOW PERMISSIONS: contents read-only")
    for item in evidence:
        print(f"{item['components']}: {item['job']} conclusion={item['conclusion']} url={item['url']}")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print("PASS: Windows, macOS, and Linux exact-commit component evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
