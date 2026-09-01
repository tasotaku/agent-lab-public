#!/usr/bin/env python3
"""Create and validate append-only artifacts for a skill-improvement loop."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def fail(message: str) -> int:
    print(json.dumps({"status": "invalid", "error": message}, ensure_ascii=False))
    return 2


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    if path.is_file():
        hasher.update(path.read_bytes())
        return hasher.hexdigest()
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        hasher.update(item.relative_to(path).as_posix().encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(item.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def inside(root: Path, value: str) -> Path:
    candidate = Path(value)
    path = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"path is outside repository: {path}") from error
    return path


def relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or "git command failed")
    return result.stdout


def changed_paths(root: Path) -> list[str]:
    tracked = git(root, "diff", "--name-only", "HEAD").splitlines()
    untracked = git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(item.replace("\\", "/") for item in tracked + untracked if item.strip()))


def is_allowed(path: str, allowed: list[str], artifact: str) -> bool:
    return any(path == item or path.startswith(item.rstrip("/") + "/") for item in allowed + [artifact])


def copy_entry(root: Path, source: Path, destination_root: Path) -> None:
    destination = destination_root / relative(root, source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)


def command_start(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    probe = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if probe.returncode != 0 or Path(probe.stdout.strip()).resolve() != root:
        return fail(f"not a Git repository root: {root}")
    if not 1 <= args.max_iterations <= 10:
        return fail("max iterations must be between 1 and 10")
    try:
        target = inside(root, args.target)
        allowed_paths = [target] + [inside(root, value) for value in args.allow_edit]
        spec = inside(root, args.spec)
        validators = [inside(root, value) for value in args.validator]
    except ValueError as error:
        return fail(str(error))
    for required in [target, spec, *validators]:
        if not required.exists():
            return fail(f"required path does not exist: {required}")
    try:
        git_status_before = git(root, "status", "--porcelain=v1")
    except ValueError as error:
        return fail(str(error))
    try:
        run_dir = inside(root, args.run_dir) if args.run_dir else None
    except ValueError as error:
        return fail(str(error))
    if run_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = root / ".loop-engineering" / "runs" / f"{stamp}-{target.name}"
    if run_dir.exists():
        return fail(f"run directory already exists: {run_dir}")
    baseline = run_dir / "baseline"
    baseline.mkdir(parents=True)
    for source in allowed_paths:
        if source.exists():
            copy_entry(root, source, baseline)
    config: dict[str, Any] = {
        "schema_version": "loop-engineering-run/v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "target": relative(root, target),
        "allowed_edit_paths": [relative(root, item) for item in allowed_paths],
        "artifact_path": relative(root, run_dir),
        "max_iterations": args.max_iterations,
        "spec": {"path": relative(root, spec), "sha256": digest(spec)},
        "validators": [{"path": relative(root, item), "sha256": digest(item)} for item in validators],
        "baseline": [
            {"path": relative(root, item), "sha256": digest(item)} for item in allowed_paths if item.exists()
        ],
        "git_status_before": git_status_before,
    }
    (run_dir / "run.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "started", "run": str(run_dir), "config": config}, ensure_ascii=False, indent=2))
    return 0


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_role_manifest(path: Path, role: str, executor_id: str) -> str | None:
    try:
        manifest = load_json(path)
    except (OSError, json.JSONDecodeError) as error:
        return f"invalid {role} input manifest: {error}"
    if not isinstance(manifest, dict):
        return f"{role} input manifest must be an object"
    if manifest.get("role") != role or manifest.get("executor_id") != executor_id:
        return f"{role} input manifest does not match its role and executor"
    provided = manifest.get("provided")
    withheld = manifest.get("withheld")
    if not isinstance(provided, list) or not all(isinstance(item, str) for item in provided):
        return f"{role} input manifest requires a string-list provided field"
    if not isinstance(withheld, list) or not all(isinstance(item, str) for item in withheld):
        return f"{role} input manifest requires a string-list withheld field"
    required = {
        "baseline": set(),
        "editor": {"held_out_cases", "expected_values"},
        "post_change": {
            "baseline_verdict", "candidate_diff", "edit_reason", "expected_answer", "prior_evaluator_text"
        },
    }[role]
    missing = sorted(required - set(withheld))
    if missing:
        return f"{role} input manifest is missing withheld items: {', '.join(missing)}"
    conflict = sorted(set(provided) & set(withheld))
    if conflict:
        return f"{role} input manifest both provides and withholds: {', '.join(conflict)}"
    return None


def diff_lines(path: Path) -> Counter[tuple[str, str, str]]:
    result: Counter[tuple[str, str, str]] = Counter()
    current = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("diff --git a/") and " b/" in line:
            current = line.split(" b/", 1)[1]
        elif current and line.startswith("+") and not line.startswith("+++"):
            result[(current, "added", line[1:])] += 1
        elif current and line.startswith("-") and not line.startswith("---"):
            result[(current, "removed", line[1:])] += 1
    return result


def validate_change_map(path: Path, patch: Path, allowed_paths: list[str], decision: str) -> str | None:
    try:
        payload = load_json(path)
    except (OSError, json.JSONDecodeError) as error:
        return f"invalid change map: {error}"
    if not isinstance(payload, dict) or not isinstance(payload.get("changes"), list):
        return "change map requires a changes list"
    mapped: Counter[tuple[str, str, str]] = Counter()
    for index, change in enumerate(payload["changes"]):
        if not isinstance(change, dict):
            return f"change map item {index} must be an object"
        changed_path = change.get("path")
        evidence = change.get("evidence_ids")
        removed = change.get("removed")
        added = change.get("added")
        if not isinstance(changed_path, str) or not any(
            changed_path == item or changed_path.startswith(item.rstrip("/") + "/") for item in allowed_paths
        ):
            return f"change map item {index} has a path outside the edit allowlist"
        if not isinstance(evidence, list) or not evidence or not all(isinstance(item, str) and item for item in evidence):
            return f"change map item {index} requires evidence IDs"
        if not isinstance(removed, list) or not isinstance(added, list):
            return f"change map item {index} requires removed and added lists"
        if not all(isinstance(item, str) for item in removed + added):
            return f"change map item {index} lines must be strings"
        for line in removed:
            mapped[(changed_path, "removed", line)] += 1
        for line in added:
            mapped[(changed_path, "added", line)] += 1
    actual = diff_lines(patch)
    if decision == "adopt" and not actual:
        return "adopt requires a non-empty candidate diff"
    if actual != mapped:
        missing = list((actual - mapped).elements())
        extra = list((mapped - actual).elements())
        return f"change map does not exactly cover candidate diff; unmapped={missing}, extra={extra}"
    return None


def command_record(args: argparse.Namespace) -> int:
    run_dir = Path(args.run).resolve()
    config_path = run_dir / "run.json"
    if not config_path.exists():
        return fail(f"run config not found: {config_path}")
    config = load_json(config_path)
    root = Path(config["root"]).resolve()
    if args.iteration < 1 or args.iteration > config["max_iterations"]:
        return fail("iteration is outside the fixed limit")
    identities = [args.baseline_executor, args.editor_executor, args.post_executor]
    if len(set(identities)) != 3:
        return fail("baseline evaluator, editor, and post evaluator must be different")
    iteration_dir = run_dir / "iterations" / f"{args.iteration:02d}"
    if iteration_dir.exists():
        return fail(f"iteration already exists and is append-only: {iteration_dir}")
    inputs: dict[str, Path] = {}
    for name in (
        "baseline_report", "post_report", "candidate_diff", "change_map", "scorecard",
        "baseline_raw", "editor_report", "post_raw", "scope_report",
        "baseline_input_manifest", "editor_input_manifest", "post_input_manifest",
    ):
        path = Path(getattr(args, name)).resolve()
        if not path.exists():
            return fail(f"missing {name}: {path}")
        inputs[name] = path
    manifest_checks = (
        (inputs["baseline_input_manifest"], "baseline", args.baseline_executor),
        (inputs["editor_input_manifest"], "editor", args.editor_executor),
        (inputs["post_input_manifest"], "post_change", args.post_executor),
    )
    for path, role, executor_id in manifest_checks:
        error = validate_role_manifest(path, role, executor_id)
        if error:
            return fail(error)
    change_map_error = validate_change_map(
        inputs["change_map"], inputs["candidate_diff"], config["allowed_edit_paths"], args.decision
    )
    if change_map_error:
        return fail(change_map_error)
    try:
        changed = changed_paths(root)
    except ValueError as error:
        return fail(str(error))
    violations = [
        path for path in changed
        if not is_allowed(path, config["allowed_edit_paths"], config["artifact_path"])
    ]
    if violations:
        return fail("changed paths outside allowlist: " + ", ".join(violations))
    iteration_dir.mkdir(parents=True)
    copied: dict[str, dict[str, str]] = {}
    for name, source in inputs.items():
        destination = iteration_dir / source.name
        shutil.copy2(source, destination)
        copied[name] = {"path": destination.name, "sha256": digest(destination)}
    record = {
        "schema_version": "loop-engineering-iteration/v1",
        "iteration": args.iteration,
        "executors": {
            "baseline": args.baseline_executor,
            "editor": args.editor_executor,
            "post_change": args.post_executor,
        },
        "artifacts": copied,
        "decision": args.decision,
        "stop_reason": args.stop_reason,
        "changed_paths": changed,
        "allowed_scope": True,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    (iteration_dir / "iteration.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "recorded", "path": str(iteration_dir), "record": record}, ensure_ascii=False, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="seal a baseline and fixed run contract")
    start.add_argument("--root", required=True)
    start.add_argument("--target", required=True)
    start.add_argument("--allow-edit", action="append", default=[])
    start.add_argument("--spec", required=True)
    start.add_argument("--validator", action="append", required=True)
    start.add_argument("--max-iterations", type=int, default=2)
    start.add_argument("--run-dir")
    record = commands.add_parser("record", help="append one evaluated iteration")
    record.add_argument("--run", required=True)
    record.add_argument("--iteration", type=int, required=True)
    record.add_argument("--baseline-executor", required=True)
    record.add_argument("--editor-executor", required=True)
    record.add_argument("--post-executor", required=True)
    record.add_argument("--baseline-report", required=True)
    record.add_argument("--baseline-raw", required=True)
    record.add_argument("--editor-report", required=True)
    record.add_argument("--post-report", required=True)
    record.add_argument("--post-raw", required=True)
    record.add_argument("--scope-report", required=True)
    record.add_argument("--candidate-diff", required=True)
    record.add_argument("--change-map", required=True)
    record.add_argument("--scorecard", required=True)
    record.add_argument("--baseline-input-manifest", required=True)
    record.add_argument("--editor-input-manifest", required=True)
    record.add_argument("--post-input-manifest", required=True)
    record.add_argument("--decision", choices=("adopt", "reject", "no-change"), required=True)
    record.add_argument("--stop-reason", required=True)
    return result


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parser().parse_args()
    return command_start(args) if args.command == "start" else command_record(args)


if __name__ == "__main__":
    raise SystemExit(main())
