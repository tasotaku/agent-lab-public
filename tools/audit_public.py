#!/usr/bin/env python3
"""Audit the public working payload and every reachable Git object."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = (
    "credentials",
    "personal_config",
    "private_knowledge",
    "conversations",
    "private_dependencies",
)
FORBIDDEN_PATH_PARTS = {
    ".agent-lab",
    ".claude",
    ".codex",
    "knowledge",
    "user-config",
}
CONVERSATION_PATH_PARTS = {"conversation", "conversations", "journal", "journals", "sessions", "interaction-reviews"}
SKIP_PARTS = {".git", ".loop-engineering", "__pycache__", ".pytest_cache", ".mypy_cache"}
TOKEN_PATTERN = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})"
)
SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:token|secret|password|api[_-]?key)\s*[:=]\s*['\"]([A-Za-z0-9_./+=-]{20,})['\"]"
)
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SAFE_EMAILS = {"example@example.com", "a@b.com"}


@dataclass(frozen=True)
class Finding:
    category: str
    ref: str
    path: str
    line: int | None
    detail: str


def git(*arguments: str) -> subprocess.CompletedProcess[bytes]:
    # Byte output preserves arbitrary historical payload for scanning;
    # only redacted finding metadata is ever emitted to stdout.
    return subprocess.run(
        ["git", "-C", str(ROOT), *arguments],
        capture_output=True,
        check=False,
    )


def worktree_files() -> list[Path]:
    # Pre-publication runs include tracked and untracked non-ignored files,
    # while local loop artifacts and caches are excluded by explicit safe roots.
    result = git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    paths = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        path = ROOT / raw.decode("utf-8", errors="surrogateescape")
        if not SKIP_PARTS.intersection(path.relative_to(ROOT).parts):
            paths.append(path)
    return paths


def git_snapshots() -> Iterable[tuple[str, str, bytes]]:
    # Every reachable commit is scanned once by object ID, which covers
    # all public branches and tags without duplicating identical ref history.
    commits = git("rev-list", "--all")
    if commits.returncode:
        raise RuntimeError(commits.stderr.decode("utf-8", errors="replace"))
    for commit in commits.stdout.decode("ascii", errors="replace").splitlines():
        listing = git("ls-tree", "-r", "-z", "--name-only", commit)
        if listing.returncode:
            raise RuntimeError(listing.stderr.decode("utf-8", errors="replace"))
        for raw in listing.stdout.split(b"\0"):
            if not raw:
                continue
            path = raw.decode("utf-8", errors="surrogateescape")
            blob = git("show", f"{commit}:{path}")
            if blob.returncode:
                raise RuntimeError(blob.stderr.decode("utf-8", errors="replace"))
            yield commit, path, blob.stdout


def absolute_path_patterns() -> tuple[re.Pattern[str], ...]:
    # Sensitive path literals are assembled at runtime so the scanner's
    # own source does not contain a false-positive example of a real home path.
    windows = "C:" + "\\" + "Users" + "\\"
    mac = "/" + "Users" + "/"
    linux = "/" + "home" + "/"
    return (
        re.compile(re.escape(windows) + r"[^\\\s]+", re.IGNORECASE),
        re.compile(re.escape(mac) + r"[^/\s]+"),
        re.compile(re.escape(linux) + r"[^/\s]+"),
    )


def scan_path(ref: str, path_text: str, data: bytes) -> list[Finding]:
    # Path classification catches private stores even when binary; text
    # patterns add line-addressable evidence without printing the matched secret.
    findings: list[Finding] = []
    normalized = path_text.replace("\\", "/")
    parts = set(Path(normalized).parts)
    if FORBIDDEN_PATH_PARTS.intersection(parts):
        findings.append(Finding("personal_config", ref, normalized, None, "forbidden private/configuration path"))
    if CONVERSATION_PATH_PARTS.intersection(parts) or normalized.lower().endswith(".jsonl"):
        findings.append(Finding("conversations", ref, normalized, None, "conversation/session path"))
    if "knowledge" in parts:
        findings.append(Finding("private_knowledge", ref, normalized, None, "private knowledge path"))

    if b"\0" in data:
        return findings
    text = data.decode("utf-8", errors="replace")
    private_key_marker = "BEGIN " + "PRIVATE KEY"
    for number, line in enumerate(text.splitlines(), start=1):
        if TOKEN_PATTERN.search(line) or SECRET_ASSIGNMENT.search(line) or private_key_marker in line:
            findings.append(Finding("credentials", ref, normalized, number, "credential-like value"))
        if any(pattern.search(line) for pattern in absolute_path_patterns()):
            findings.append(Finding("personal_config", ref, normalized, number, "absolute user-home path"))
        for email in EMAIL_PATTERN.findall(line):
            if email.lower() not in SAFE_EMAILS:
                findings.append(Finding("personal_config", ref, normalized, number, "personal email-like value"))
        private_repo = "github.com/" + "tasotaku" + "/" + "agent-lab"
        if private_repo in line and private_repo + "-public" not in line:
            findings.append(Finding("private_dependencies", ref, normalized, number, "private repository dependency"))
    return findings


def scan_commit_messages() -> tuple[list[Finding], int]:
    # Commit subjects/bodies are public payload too; scan them with the
    # same redacted detectors while retaining the commit as the object locator.
    result = git("log", "--all", "--format=%H%x00%B%x00")
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    fields = [field for field in result.stdout.split(b"\0") if field]
    findings: list[Finding] = []
    count = 0
    for index in range(0, len(fields) - 1, 2):
        commit = fields[index].decode("ascii", errors="replace").strip()
        message = fields[index + 1]
        findings.extend(scan_path(commit, "<commit-message>", message))
        count += 1
    return findings, count


def refs() -> list[str]:
    # Ref names are enumerated in the report so a reviewer can tell that
    # the audit was not silently limited to the checked-out default branch.
    result = git("for-each-ref", "--format=%(refname)")
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
    return [line for line in result.stdout.decode("utf-8", errors="replace").splitlines() if line]


def symlink_findings(paths: Iterable[Path]) -> list[Finding]:
    # Public symlinks may only target descendants of the clone, avoiding
    # machine paths and accidental disclosure through escaping links.
    findings: list[Finding] = []
    for path in paths:
        if not path.is_symlink():
            continue
        try:
            path.resolve().relative_to(ROOT)
        except (OSError, ValueError):
            findings.append(Finding("private_dependencies", "WORKTREE", path.relative_to(ROOT).as_posix(), None, "symlink escapes public clone"))
    return findings


def audit() -> dict[str, object]:
    # Working payload and immutable history are both classified, and an
    # empty tree cannot appear healthy because scanned counts remain visible.
    findings: list[Finding] = []
    paths = worktree_files()
    file_count = 0
    for path in paths:
        if path.is_file() or path.is_symlink():
            findings.extend(scan_path("WORKTREE", path.relative_to(ROOT).as_posix(), path.read_bytes()))
            file_count += 1
    findings.extend(symlink_findings(paths))

    historical_files = 0
    commits: set[str] = set()
    for commit, path_text, data in git_snapshots():
        findings.extend(scan_path(commit, path_text, data))
        historical_files += 1
        commits.add(commit)
    commit_findings, commit_message_count = scan_commit_messages()
    findings.extend(commit_findings)
    categories = {
        category: "FAIL" if any(finding.category == category for finding in findings) else "PASS"
        for category in CATEGORIES
    }
    return {
        "verdict": "PASS" if not findings else "FAIL",
        "categories": categories,
        "scanned": {
            "refs": refs(),
            "commits": max(len(commits), commit_message_count),
            "files": file_count,
            "historical_files": historical_files,
            "ignored_non_public_roots": sorted(SKIP_PARTS),
        },
        "findings": [asdict(finding) for finding in findings],
    }


def print_text(report: dict[str, object]) -> None:
    # Human output leads with category verdicts, then scope, then precise
    # redacted locators, matching the README's reproducible review contract.
    categories = report["categories"]
    assert isinstance(categories, dict)
    labels = {
        "credentials": "credentials",
        "personal_config": "personal configuration",
        "private_knowledge": "private knowledge / customer data",
        "conversations": "conversations",
        "private_dependencies": "private dependencies",
    }
    for key in CATEGORIES:
        print(f"{categories[key]}: {labels[key]}")
    scanned = report["scanned"]
    assert isinstance(scanned, dict)
    print(
        "SCANNED: "
        f"refs={len(scanned['refs'])} commits={scanned['commits']} "
        f"working_files={scanned['files']} historical_files={scanned['historical_files']}"
    )
    findings = report["findings"]
    assert isinstance(findings, list)
    for finding in findings:
        assert isinstance(finding, dict)
        location = f"{finding['ref']}:{finding['path']}"
        if finding["line"] is not None:
            location += f":{finding['line']}"
        print(f"FINDING: {finding['category']} {location} {finding['detail']}")
    print(f"{report['verdict']}: public payload audit")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()
    try:
        report = audit()
    except (OSError, RuntimeError) as error:
        print(f"FAIL: audit could not enumerate public payload: {error}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text(report)
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
